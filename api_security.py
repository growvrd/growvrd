"""
API security middleware for GrowVRD API.

This module provides authentication, authorization, rate limiting,
and input validation for protecting API endpoints.
"""
import logging
import time
import functools
import re
import json
import hmac
import hashlib
from typing import Dict, List, Any, Optional, Callable, Set, Tuple, Union
from datetime import datetime, timedelta
from threading import RLock

from flask import request, g, jsonify, current_app
from werkzeug.security import check_password_hash

from core.oauth_sheets_connector import get_user_by_email, get_user_subscription_status
from api_response import APIResponse, ERROR_AUTHENTICATION, ERROR_AUTHORIZATION, ERROR_RATE_LIMIT

# Set up logging
logger = logging.getLogger('api_security')

# Rate limit storage (in-memory for development, should use Redis in production)
_rate_limits = {}
_rate_limit_lock = RLock()

# API key storage (in-memory for development, should use secure database in production)
# Format: {api_key: {'user_id': '...', 'permissions': [...]}}
_api_keys = {}

# Blacklisted tokens (for logout/revocation)
_blacklisted_tokens = set()


class AuthError(Exception):
    """Exception raised for authentication and authorization errors"""

    def __init__(self, message: str, error_type: str = ERROR_AUTHENTICATION):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


def _extract_api_key() -> Optional[str]:
    """
    Extract API key from request headers.

    Returns:
        API key if found, None otherwise
    """
    # Try different header formats
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        api_key = request.headers.get('Authorization')
        if api_key and api_key.startswith('Bearer '):
            api_key = api_key[7:]  # Remove 'Bearer ' prefix

    return api_key


def _extract_user_token() -> Tuple[Optional[str], Optional[str]]:
    """
    Extract user credentials from request.

    Returns:
        Tuple of (user_email, token) if found, (None, None) otherwise
    """
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Check if token is in user_id:token format
        if ':' in token:
            user_id, actual_token = token.split(':', 1)
            return user_id, actual_token

    # Try to get from request parameters
    user_id = request.args.get('user_id') or request.form.get('user_id')
    token = request.args.get('token') or request.form.get('token')

    if user_id and token:
        return user_id, token

    return None, None


def require_api_key(permissions: Optional[List[str]] = None):
    """
    Decorator to require API key authentication with specific permissions.

    Args:
        permissions: List of required permissions

    Returns:
        Decorated function
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = _extract_api_key()

            if not api_key:
                return jsonify(APIResponse.authentication_error(
                    message="API key required",
                    details={"header": "Missing 'X-API-Key' or 'Authorization: Bearer' header"}
                )), 401

            # Validate API key
            if api_key not in _api_keys:
                return jsonify(APIResponse.authentication_error(
                    message="Invalid API key",
                    details={"error": "The provided API key is not valid"}
                )), 401

            # Check permissions
            if permissions:
                user_permissions = _api_keys[api_key].get('permissions', [])
                missing_permissions = [p for p in permissions if p not in user_permissions]

                if missing_permissions:
                    return jsonify(APIResponse.authorization_error(
                        message="Insufficient permissions",
                        details={"missing_permissions": missing_permissions}
                    )), 403

            # Store user info in Flask's g object for access in the view function
            g.user_id = _api_keys[api_key].get('user_id')
            g.permissions = _api_keys[api_key].get('permissions', [])

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_user_auth(required_subscription: Optional[str] = None):
    """
    Decorator to require user authentication with optional subscription check.

    Args:
        required_subscription: Required subscription level ('subscriber', 'premium')

    Returns:
        Decorated function
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            email, token = _extract_user_token()

            if not email or not token:
                return jsonify(APIResponse.authentication_error(
                    message="Authentication required",
                    details={"error": "Missing or invalid authentication credentials"}
                )), 401

            # Check if token is blacklisted (logged out)
            token_hash = hashlib.md5(f"{email}:{token}".encode()).hexdigest()
            if token_hash in _blacklisted_tokens:
                return jsonify(APIResponse.authentication_error(
                    message="Invalid or expired token",
                    details={"error": "Token has been revoked or expired"}
                )), 401

            # Validate user credentials (in a real app, use proper password comparison)
            try:
                user = get_user_by_email(email)
                if not user:
                    return jsonify(APIResponse.authentication_error(
                        message="Invalid credentials",
                        details={"error": "User not found"}
                    )), 401

                # Validate token (this is a placeholder - implement proper token validation)
                saved_token = user.get('auth_token', '')
                if not saved_token or saved_token != token:
                    return jsonify(APIResponse.authentication_error(
                        message="Invalid credentials",
                        details={"error": "Invalid token"}
                    )), 401

                # Check subscription level if required
                if required_subscription:
                    user_subscription = get_user_subscription_status(email)
                    if user_subscription != required_subscription:
                        return jsonify(APIResponse.authorization_error(
                            message=f"{required_subscription.title()} subscription required",
                            details={
                                "required": required_subscription,
                                "current": user_subscription,
                                "upgrade_url": "/api/subscriptions/upgrade"
                            }
                        )), 403

                # Store user info in Flask's g object
                g.user = user
                g.user_email = email
                g.subscription = user.get('subscription_status', 'free')

                return f(*args, **kwargs)

            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                return jsonify(APIResponse.authentication_error(
                    message="Authentication failed",
                    details={"error": str(e)}
                )), 401

        return decorated_function

    return decorator


def rate_limit(limit: int, period: int = 60, by_ip: bool = True, by_user: bool = True):
    """
    Decorator to apply rate limiting to API endpoints.

    Args:
        limit: Maximum number of requests allowed in the period
        period: Time period in seconds
        by_ip: Whether to limit by IP address
        by_user: Whether to limit by authenticated user

    Returns:
        Decorated function
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Determine the rate limit key
            key_parts = []

            if by_ip:
                # Get the client's IP address
                ip = request.remote_addr
                key_parts.append(f"ip:{ip}")

            if by_user and hasattr(g, 'user_email'):
                key_parts.append(f"user:{g.user_email}")
            elif by_user and hasattr(g, 'user_id'):
                key_parts.append(f"user:{g.user_id}")

            # If no key parts, no rate limiting
            if not key_parts:
                return f(*args, **kwargs)

            # Create the rate limit key
            endpoint = request.endpoint or request.path
            key = f"ratelimit:{endpoint}:{'.'.join(key_parts)}"

            # Check rate limit
            with _rate_limit_lock:
                now = time.time()

                # Initialize or clean up record
                if key not in _rate_limits:
                    _rate_limits[key] = {
                        'reset_at': now + period,
                        'remaining': limit,
                        'count': 0
                    }
                elif _rate_limits[key]['reset_at'] <= now:
                    # Reset if period has passed
                    _rate_limits[key] = {
                        'reset_at': now + period,
                        'remaining': limit,
                        'count': 0
                    }

                # Check if limit exceeded
                if _rate_limits[key]['remaining'] <= 0:
                    retry_after = int(_rate_limits[key]['reset_at'] - now)

                    # Set rate limit headers
                    headers = {
                        'X-RateLimit-Limit': str(limit),
                        'X-RateLimit-Remaining': '0',
                        'X-RateLimit-Reset': str(int(_rate_limits[key]['reset_at'])),
                        'Retry-After': str(retry_after)
                    }

                    response = jsonify(APIResponse.rate_limit_error(
                        message="Rate limit exceeded",
                        retry_after=retry_after
                    ))

                    # Add headers to response
                    for header, value in headers.items():
                        response.headers[header] = value

                    return response, 429

                # Update rate limit counter
                _rate_limits[key]['count'] += 1
                _rate_limits[key]['remaining'] -= 1

                # Set rate limit headers for the actual response
                response = f(*args, **kwargs)

                if isinstance(response, tuple):
                    response_obj, status_code = response
                else:
                    response_obj, status_code = response, 200

                # Add headers if it's a Flask response
                if hasattr(response_obj, 'headers'):
                    response_obj.headers['X-RateLimit-Limit'] = str(limit)
                    response_obj.headers['X-RateLimit-Remaining'] = str(_rate_limits[key]['remaining'])
                    response_obj.headers['X-RateLimit-Reset'] = str(int(_rate_limits[key]['reset_at']))

                return response

        return decorated_function

    return decorator


def validate_input(schema: Dict[str, Any], source: str = 'json'):
    """
    Decorator to validate request input against a schema.

    Args:
        schema: JSON schema for validation
        source: Where to look for input data ('json', 'form', 'args')

    Returns:
        Decorated function
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Get input data from the appropriate source
            if source == 'json':
                try:
                    data = request.get_json(silent=True) or {}
                except Exception:
                    return jsonify(APIResponse.validation_error(
                        message="Invalid JSON in request body",
                        validation_errors={"body": "Could not parse JSON"}
                    )), 400
            elif source == 'form':
                data = request.form.to_dict()
            elif source == 'args':
                data = request.args.to_dict()
            else:
                data = {}

            # Simple schema validation (replace with jsonschema in production)
            validation_errors = {}

            for field, field_schema in schema.items():
                field_type = field_schema.get('type')
                required = field_schema.get('required', False)

                # Check required fields
                if required and (field not in data or data[field] is None or data[field] == ''):
                    validation_errors[field] = f"Field '{field}' is required"
                    continue

                # Skip validation for non-required fields that are not present
                if field not in data:
                    continue

                # Type validation
                if field_type == 'string':
                    if not isinstance(data[field], str):
                        validation_errors[field] = f"Field '{field}' must be a string"
                elif field_type == 'integer':
                    try:
                        data[field] = int(data[field])
                    except (ValueError, TypeError):
                        validation_errors[field] = f"Field '{field}' must be an integer"
                elif field_type == 'number':
                    try:
                        data[field] = float(data[field])
                    except (ValueError, TypeError):
                        validation_errors[field] = f"Field '{field}' must be a number"
                elif field_type == 'boolean':
                    if isinstance(data[field], str):
                        data[field] = data[field].lower() in ('true', 'yes', '1', 't', 'y')
                    else:
                        try:
                            data[field] = bool(data[field])
                        except (ValueError, TypeError):
                            validation_errors[field] = f"Field '{field}' must be a boolean"
                elif field_type == 'array':
                    if isinstance(data[field], str):
                        # Try to parse as JSON array
                        try:
                            data[field] = json.loads(data[field])
                            if not isinstance(data[field], list):
                                validation_errors[field] = f"Field '{field}' must be an array"
                        except json.JSONDecodeError:
                            # Try to parse as comma-separated list
                            data[field] = [item.strip() for item in data[field].split(',')]
                    elif not isinstance(data[field], list):
                        validation_errors[field] = f"Field '{field}' must be an array"

                # Pattern validation (for strings)
                pattern = field_schema.get('pattern')
                if pattern and isinstance(data[field], str):
                    if not re.match(pattern, data[field]):
                        validation_errors[field] = field_schema.get(
                            'pattern_error',
                            f"Field '{field}' does not match the required pattern"
                        )

                # Enum validation (value must be one of the provided options)
                enum = field_schema.get('enum')
                if enum and data[field] not in enum:
                    validation_errors[field] = field_schema.get(
                        'enum_error',
                        f"Field '{field}' must be one of: {', '.join(map(str, enum))}"
                    )

                # Minimum/maximum validation (for numbers)
                if field_type in ('integer', 'number'):
                    minimum = field_schema.get('minimum')
                    maximum = field_schema.get('maximum')

                    if minimum is not None and data[field] < minimum:
                        validation_errors[field] = field_schema.get(
                            'minimum_error',
                            f"Field '{field}' must be at least {minimum}"
                        )

                    if maximum is not None and data[field] > maximum:
                        validation_errors[field] = field_schema.get(
                            'maximum_error',
                            f"Field '{field}' must be at most {maximum}"
                        )

                # Length validation (for strings and arrays)
                if field_type in ('string', 'array'):
                    min_length = field_schema.get('minLength')
                    max_length = field_schema.get('maxLength')

                    if min_length is not None and len(data[field]) < min_length:
                        validation_errors[field] = field_schema.get(
                            'min_length_error',
                            f"Field '{field}' must be at least {min_length} characters long"
                        )

                    if max_length is not None and len(data[field]) > max_length:
                        validation_errors[field] = field_schema.get(
                            'max_length_error',
                            f"Field '{field}' must be at most {max_length} characters long"
                        )

            # If there are validation errors, return them
            if validation_errors:
                return jsonify(APIResponse.validation_error(
                    message="Validation error",
                    validation_errors=validation_errors
                )), 400

            # Store validated data in Flask's g object for access in the view function
            g.validated_data = data

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def sanitize_input(raw_input: str) -> str:
    """
    Sanitize input to prevent XSS and injection attacks.

    Args:
        raw_input: Input string to sanitize

    Returns:
        Sanitized string
    """
    # Basic sanitization - this is not comprehensive!
    # For production, use a robust library like bleach

    # Replace potentially dangerous characters
    sanitized = re.sub(r'[<>"\'&]', '', raw_input)

    # Prevent SQL injection attempts
    sanitized = re.sub(r'(\b(select|insert|update|delete|drop|alter|union|exec|execute|declare|where)\b)',
                       '', sanitized, flags=re.IGNORECASE)

    return sanitized


def validate_recaptcha(recaptcha_token: str) -> bool:
    """
    Validate a reCAPTCHA token with Google's reCAPTCHA API.

    Args:
        recaptcha_token: reCAPTCHA response token from client

    Returns:
        True if verification succeeds, False otherwise
    """
    import requests

    # Get reCAPTCHA secret key from environment
    secret_key = current_app.config.get('RECAPTCHA_SECRET_KEY')
    if not secret_key:
        logger.warning("reCAPTCHA secret key not configured")
        return False

    # Verify with Google's API
    response = requests.post(
        'https://www.google.com/recaptcha/api/siteverify',
        data={
            'secret': secret_key,
            'response': recaptcha_token,
            'remoteip': request.remote_addr
        }
    )

    try:
        result = response.json()
        return result.get('success', False)
    except Exception as e:
        logger.error(f"reCAPTCHA verification error: {str(e)}")
        return False


def require_recaptcha(f):
    """
    Decorator to require reCAPTCHA verification for sensitive endpoints.

    Args:
        f: Function to decorate

    Returns:
        Decorated function
    """

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Get reCAPTCHA token from request
        token = request.form.get('g-recaptcha-response') or request.headers.get('X-Recaptcha-Token')

        if not token:
            return jsonify(APIResponse.validation_error(
                message="reCAPTCHA verification required",
                validation_errors={"recaptcha": "Missing reCAPTCHA token"}
            )), 400

        # Verify token
        if not validate_recaptcha(token):
            return jsonify(APIResponse.validation_error(
                message="reCAPTCHA verification failed",
                validation_errors={"recaptcha": "Invalid or expired reCAPTCHA token"}
            )), 400

        return f(*args, **kwargs)

    return decorated_function


def setup_security(app):
    """
    Set up security middleware for a Flask application.

    Args:
        app: Flask application instance
    """

    # Register a before_request handler to sanitize all inputs
    @app.before_request
    def before_request():
        # Sanitize form data
        if request.form:
            for key, value in request.form.items():
                if isinstance(value, str):
                    request.form[key] = sanitize_input(value)

        # Sanitize query parameters
        if request.args:
            for key, value in request.args.items():
                if isinstance(value, str):
                    request.args[key] = sanitize_input(value)

    # Register error handlers
    @app.errorhandler(AuthError)
    def handle_auth_error(e):
        if e.error_type == ERROR_AUTHENTICATION:
            return jsonify(APIResponse.authentication_error(message=e.message)), 401
        else:
            return jsonify(APIResponse.authorization_error(message=e.message)), 403


def generate_api_key(user_id: str, permissions: List[str] = None) -> str:
    """
    Generate a new API key for a user.

    Args:
        user_id: User ID
        permissions: List of permissions to grant

    Returns:
        Generated API key
    """
    # Generate a random API key
    import secrets
    api_key = f"gvrd_{secrets.token_hex(16)}"

    # Store API key
    _api_keys[api_key] = {
        'user_id': user_id,
        'permissions': permissions or [],
        'created_at': datetime.now().isoformat()
    }

    return api_key


def revoke_api_key(api_key: str) -> bool:
    """
    Revoke an API key.

    Args:
        api_key: API key to revoke

    Returns:
        True if key was found and revoked, False otherwise
    """
    if api_key in _api_keys:
        del _api_keys[api_key]
        return True
    return False


def revoke_user_token(email: str, token: str) -> bool:
    """
    Revoke a user authentication token (logout).

    Args:
        email: User email
        token: Authentication token

    Returns:
        True if token was blacklisted, False if operation failed
    """
    try:
        # Calculate token hash for blacklist
        token_hash = hashlib.md5(f"{email}:{token}".encode()).hexdigest()

        # Add to blacklist
        _blacklisted_tokens.add(token_hash)

        # Clean up expired tokens (should use task queue in production)
        _cleanup_blacklisted_tokens()

        return True
    except Exception as e:
        logger.error(f"Error revoking token: {str(e)}")
        return False


def _cleanup_blacklisted_tokens() -> None:
    """
    Clean up blacklisted tokens (this is a placeholder).

    In production, tokens should have expiration times and be stored
    in a persistent store like Redis with automatic expiration.
    """
    # For demonstration only - in a real application, use Redis TTL
    # Here we just limit the size of the blacklist to prevent memory issues
    max_blacklist_size = 1000
    if len(_blacklisted_tokens) > max_blacklist_size:
        # Remove some tokens (random approach for demo only)
        # In production, you'd remove the oldest tokens
        excess = len(_blacklisted_tokens) - max_blacklist_size
        for _ in range(excess):
            try:
                _blacklisted_tokens.pop()
            except KeyError:
                pass


# Add some example API keys for testing
_api_keys['test_api_key'] = {
    'user_id': 'test_user',
    'permissions': ['read', 'write'],
    'created_at': datetime.now().isoformat()
}

# Flask route decorators usage examples

# Example 1: Simple API key auth
"""
@app.route('/api/secure-endpoint')
@require_api_key(['read'])
def secure_endpoint():
    return jsonify({'message': 'This is a secure endpoint'})
"""

# Example 2: User auth with subscription check
"""
@app.route('/api/subscriber-endpoint')
@require_user_auth(required_subscription='subscriber')
def subscriber_endpoint():
    return jsonify({'message': 'This is a subscriber-only endpoint'})
"""

# Example 3: Rate limiting
"""
@app.route('/api/limited-endpoint')
@rate_limit(limit=10, period=60)
def limited_endpoint():
    return jsonify({'message': 'This endpoint is rate limited'})
"""

# Example 4: Input validation
"""
user_schema = {
    'email': {
        'type': 'string',
        'required': True,
        'pattern': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,},
        'pattern_error': 'Email format is invalid'
    },
    'name': {
        'type': 'string',
        'required': True,
        'minLength': 2,
        'maxLength': 50
    },
    'age': {
        'type': 'integer',
        'minimum': 18,
        'maximum': 120
    }
}

@app.route('/api/create-user', methods=['POST'])
@validate_input(schema=user_schema, source='json')
def create_user():
    # g.validated_data contains sanitized and validated input
    return jsonify({'message': 'User created', 'user': g.validated_data})
"""

# Example 5: Combining multiple security measures
"""
@app.route('/api/secure-create', methods=['POST'])
@require_api_key(['write'])
@rate_limit(limit=5, period=60)
@validate_input(schema=user_schema, source='json')
def secure_create():
    return jsonify({'message': 'Secure create endpoint'})
"""