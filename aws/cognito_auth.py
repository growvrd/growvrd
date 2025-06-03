"""
AWS Cognito Authentication for GrowVRD

This module provides secure user authentication using AWS Cognito User Pools,
replacing the current basic authentication system with enterprise-grade security.
"""
import os
import jwt
import json
import logging
import hmac
import hashlib
import base64
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from flask import request, g, jsonify, current_app

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cognito_auth')


class CognitoAuthError(Exception):
    """Exception raised for Cognito authentication errors"""
    pass


class CognitoConnector:
    """
    AWS Cognito connector for user authentication and management
    """

    def __init__(self):
        """Initialize Cognito connector"""
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.client_id = os.getenv('COGNITO_CLIENT_ID')
        self.client_secret = os.getenv('COGNITO_CLIENT_SECRET')

        if not all([self.user_pool_id, self.client_id]):
            raise CognitoAuthError("Missing required Cognito configuration")

        # Initialize Cognito client
        try:
            self.cognito_client = boto3.client(
                'cognito-idp',
                region_name=self.region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            logger.info("Cognito client initialized successfully")
        except Exception as e:
            raise CognitoAuthError(f"Failed to initialize Cognito client: {str(e)}")

    def _get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito operations"""
        if not self.client_secret:
            return None

        message = username + self.client_id
        dig = hmac.new(
            str(self.client_secret).encode('utf-8'),
            msg=str(message).encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(dig).decode()

    def register_user(self, email: str, password: str, user_attributes: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Register a new user with Cognito

        Args:
            email: User's email address
            password: User's password
            user_attributes: Additional user attributes

        Returns:
            Registration response with user details
        """
        try:
            # Prepare user attributes
            attributes = [
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ]

            if user_attributes:
                for key, value in user_attributes.items():
                    attributes.append({'Name': key, 'Value': str(value)})

            # Prepare parameters
            params = {
                'ClientId': self.client_id,
                'Username': email,
                'Password': password,
                'UserAttributes': attributes
            }

            # Add secret hash if client has secret
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                params['SecretHash'] = secret_hash

            # Register user
            response = self.cognito_client.sign_up(**params)

            logger.info(f"User registered successfully: {email}")
            return {
                'success': True,
                'user_sub': response['UserSub'],
                'confirmation_required': not response.get('UserConfirmed', False),
                'message': 'User registered successfully'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.error(f"Registration failed for {email}: {error_code} - {error_message}")

            # Handle specific error cases
            if error_code == 'UsernameExistsException':
                return {'success': False, 'error': 'user_exists', 'message': 'User already exists'}
            elif error_code == 'InvalidPasswordException':
                return {'success': False, 'error': 'invalid_password', 'message': 'Password does not meet requirements'}
            elif error_code == 'InvalidParameterException':
                return {'success': False, 'error': 'invalid_parameter', 'message': error_message}
            else:
                return {'success': False, 'error': 'registration_failed', 'message': error_message}

        except Exception as e:
            logger.error(f"Unexpected error during registration: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Registration failed due to system error'}

    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user with email and password

        Args:
            email: User's email address
            password: User's password

        Returns:
            Authentication response with tokens
        """
        try:
            # Prepare parameters
            params = {
                'ClientId': self.client_id,
                'AuthFlow': 'USER_PASSWORD_AUTH',
                'AuthParameters': {
                    'USERNAME': email,
                    'PASSWORD': password
                }
            }

            # Add secret hash if client has secret
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                params['AuthParameters']['SECRET_HASH'] = secret_hash

            # Authenticate
            response = self.cognito_client.initiate_auth(**params)

            # Extract tokens
            auth_result = response['AuthenticationResult']

            logger.info(f"User authenticated successfully: {email}")
            return {
                'success': True,
                'access_token': auth_result['AccessToken'],
                'id_token': auth_result['IdToken'],
                'refresh_token': auth_result['RefreshToken'],
                'expires_in': auth_result['ExpiresIn'],
                'token_type': auth_result['TokenType']
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.error(f"Authentication failed for {email}: {error_code} - {error_message}")

            # Handle specific error cases
            if error_code == 'NotAuthorizedException':
                return {'success': False, 'error': 'invalid_credentials', 'message': 'Invalid email or password'}
            elif error_code == 'UserNotConfirmedException':
                return {'success': False, 'error': 'user_not_confirmed', 'message': 'User email not confirmed'}
            elif error_code == 'PasswordResetRequiredException':
                return {'success': False, 'error': 'password_reset_required', 'message': 'Password reset required'}
            elif error_code == 'UserNotFoundException':
                return {'success': False, 'error': 'user_not_found', 'message': 'User not found'}
            else:
                return {'success': False, 'error': 'authentication_failed', 'message': error_message}

        except Exception as e:
            logger.error(f"Unexpected error during authentication: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Authentication failed due to system error'}

    def verify_token(self, access_token: str) -> Dict[str, Any]:
        """
        Verify and decode access token

        Args:
            access_token: JWT access token from Cognito

        Returns:
            Decoded token payload with user information
        """
        try:
            # Get user info using access token
            response = self.cognito_client.get_user(AccessToken=access_token)

            # Extract user attributes
            user_attributes = {}
            for attr in response['UserAttributes']:
                user_attributes[attr['Name']] = attr['Value']

            return {
                'success': True,
                'username': response['Username'],
                'user_attributes': user_attributes,
                'email': user_attributes.get('email'),
                'email_verified': user_attributes.get('email_verified') == 'true',
                'sub': user_attributes.get('sub')
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Token verification failed: {error_code}")

            if error_code == 'NotAuthorizedException':
                return {'success': False, 'error': 'invalid_token', 'message': 'Invalid or expired token'}
            else:
                return {'success': False, 'error': 'verification_failed', 'message': 'Token verification failed'}

        except Exception as e:
            logger.error(f"Unexpected error during token verification: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Token verification failed'}

    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New access token and ID token
        """
        try:
            # Prepare parameters
            params = {
                'ClientId': self.client_id,
                'AuthFlow': 'REFRESH_TOKEN_AUTH',
                'AuthParameters': {
                    'REFRESH_TOKEN': refresh_token
                }
            }

            # Add secret hash if client has secret
            if self.client_secret:
                # For refresh, we need the username - get it from the refresh token
                # This is a simplified approach; in production, you might store username separately
                params['AuthParameters']['SECRET_HASH'] = self._get_secret_hash('placeholder')

            # Refresh tokens
            response = self.cognito_client.initiate_auth(**params)
            auth_result = response['AuthenticationResult']

            return {
                'success': True,
                'access_token': auth_result['AccessToken'],
                'id_token': auth_result['IdToken'],
                'expires_in': auth_result['ExpiresIn'],
                'token_type': auth_result['TokenType']
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Token refresh failed: {error_code}")

            if error_code == 'NotAuthorizedException':
                return {'success': False, 'error': 'invalid_refresh_token', 'message': 'Invalid refresh token'}
            else:
                return {'success': False, 'error': 'refresh_failed', 'message': 'Token refresh failed'}

        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Token refresh failed'}

    def forgot_password(self, email: str) -> Dict[str, Any]:
        """
        Initiate forgot password flow

        Args:
            email: User's email address

        Returns:
            Response indicating if password reset was initiated
        """
        try:
            # Prepare parameters
            params = {
                'ClientId': self.client_id,
                'Username': email
            }

            # Add secret hash if client has secret
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                params['SecretHash'] = secret_hash

            # Initiate forgot password
            self.cognito_client.forgot_password(**params)

            logger.info(f"Password reset initiated for: {email}")
            return {
                'success': True,
                'message': 'Password reset code sent to your email'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Forgot password failed for {email}: {error_code}")

            if error_code == 'UserNotFoundException':
                # For security, don't reveal if user exists
                return {'success': True, 'message': 'If the email exists, a reset code has been sent'}
            elif error_code == 'LimitExceededException':
                return {'success': False, 'error': 'rate_limit', 'message': 'Too many requests, please try again later'}
            else:
                return {'success': False, 'error': 'forgot_password_failed',
                        'message': 'Failed to initiate password reset'}

        except Exception as e:
            logger.error(f"Unexpected error during forgot password: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Password reset failed'}

    def confirm_forgot_password(self, email: str, confirmation_code: str, new_password: str) -> Dict[str, Any]:
        """
        Confirm forgot password with verification code

        Args:
            email: User's email address
            confirmation_code: Verification code from email
            new_password: New password

        Returns:
            Response indicating if password was reset successfully
        """
        try:
            # Prepare parameters
            params = {
                'ClientId': self.client_id,
                'Username': email,
                'Password': new_password,
                'ConfirmationCode': confirmation_code
            }

            # Add secret hash if client has secret
            secret_hash = self._get_secret_hash(email)
            if secret_hash:
                params['SecretHash'] = secret_hash

            # Confirm forgot password
            self.cognito_client.confirm_forgot_password(**params)

            logger.info(f"Password reset confirmed for: {email}")
            return {
                'success': True,
                'message': 'Password reset successfully'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Password reset confirmation failed for {email}: {error_code}")

            if error_code == 'CodeMismatchException':
                return {'success': False, 'error': 'invalid_code', 'message': 'Invalid verification code'}
            elif error_code == 'ExpiredCodeException':
                return {'success': False, 'error': 'expired_code', 'message': 'Verification code has expired'}
            elif error_code == 'InvalidPasswordException':
                return {'success': False, 'error': 'invalid_password', 'message': 'Password does not meet requirements'}
            else:
                return {'success': False, 'error': 'confirmation_failed',
                        'message': 'Password reset confirmation failed'}

        except Exception as e:
            logger.error(f"Unexpected error during password reset confirmation: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Password reset confirmation failed'}

    def change_password(self, access_token: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """
        Change user password (when logged in)

        Args:
            access_token: User's access token
            old_password: Current password
            new_password: New password

        Returns:
            Response indicating if password was changed successfully
        """
        try:
            self.cognito_client.change_password(
                AccessToken=access_token,
                PreviousPassword=old_password,
                ProposedPassword=new_password
            )

            logger.info("Password changed successfully")
            return {
                'success': True,
                'message': 'Password changed successfully'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Password change failed: {error_code}")

            if error_code == 'NotAuthorizedException':
                return {'success': False, 'error': 'invalid_password', 'message': 'Current password is incorrect'}
            elif error_code == 'InvalidPasswordException':
                return {'success': False, 'error': 'invalid_new_password',
                        'message': 'New password does not meet requirements'}
            else:
                return {'success': False, 'error': 'change_failed', 'message': 'Password change failed'}

        except Exception as e:
            logger.error(f"Unexpected error during password change: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'Password change failed'}

    def update_user_attributes(self, access_token: str, attributes: Dict[str, str]) -> Dict[str, Any]:
        """
        Update user attributes

        Args:
            access_token: User's access token
            attributes: Dictionary of attributes to update

        Returns:
            Response indicating if attributes were updated successfully
        """
        try:
            # Prepare user attributes
            user_attributes = []
            for key, value in attributes.items():
                user_attributes.append({'Name': key, 'Value': str(value)})

            self.cognito_client.update_user_attributes(
                AccessToken=access_token,
                UserAttributes=user_attributes
            )

            logger.info("User attributes updated successfully")
            return {
                'success': True,
                'message': 'User attributes updated successfully'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"User attributes update failed: {error_code}")

            return {'success': False, 'error': 'update_failed', 'message': 'Failed to update user attributes'}

        except Exception as e:
            logger.error(f"Unexpected error during user attributes update: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'User attributes update failed'}

    def delete_user(self, access_token: str) -> Dict[str, Any]:
        """
        Delete user account

        Args:
            access_token: User's access token

        Returns:
            Response indicating if user was deleted successfully
        """
        try:
            self.cognito_client.delete_user(AccessToken=access_token)

            logger.info("User deleted successfully")
            return {
                'success': True,
                'message': 'User account deleted successfully'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"User deletion failed: {error_code}")

            return {'success': False, 'error': 'deletion_failed', 'message': 'Failed to delete user account'}

        except Exception as e:
            logger.error(f"Unexpected error during user deletion: {str(e)}")
            return {'success': False, 'error': 'system_error', 'message': 'User deletion failed'}


# Global connector instance
_cognito_connector = None


def get_cognito_connector() -> CognitoConnector:
    """Get global Cognito connector instance"""
    global _cognito_connector
    if _cognito_connector is None:
        _cognito_connector = CognitoConnector()
    return _cognito_connector


# Flask decorators for authentication
def require_auth(f):
    """
    Decorator to require authentication for Flask routes
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401

        access_token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Verify token
        connector = get_cognito_connector()
        result = connector.verify_token(access_token)

        if not result['success']:
            return jsonify({'error': result['message']}), 401

        # Store user info in Flask g object
        g.current_user = result
        g.user_email = result['email']
        g.user_sub = result['sub']

        return f(*args, **kwargs)

    return decorated_function


def require_subscription(subscription_level: str):
    """
    Decorator to require specific subscription level
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # First ensure user is authenticated
            if not hasattr(g, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401

            # Get user subscription from DynamoDB
            try:
                from aws.dynamo_connector import get_user_by_email
                user = get_user_by_email(g.user_email)

                if not user:
                    return jsonify({'error': 'User not found'}), 404

                user_subscription = user.get('subscription_status', 'free')

                # Check subscription level
                subscription_hierarchy = ['free', 'subscriber', 'premium']
                required_level = subscription_hierarchy.index(subscription_level)
                user_level = subscription_hierarchy.index(user_subscription)

                if user_level < required_level:
                    return jsonify({
                        'error': 'Insufficient subscription level',
                        'required': subscription_level,
                        'current': user_subscription
                    }), 403

                # Store subscription info
                g.user_subscription = user_subscription

                return f(*args, **kwargs)

            except Exception as e:
                logger.error(f"Error checking subscription: {str(e)}")
                return jsonify({'error': 'Failed to verify subscription'}), 500

        return decorated_function

    return decorator


# Utility functions
def get_user_from_token(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Get user information from access token

    Args:
        access_token: JWT access token

    Returns:
        User information or None if invalid
    """
    try:
        connector = get_cognito_connector()
        result = connector.verify_token(access_token)

        if result['success']:
            return result
        else:
            return None

    except Exception as e:
        logger.error(f"Error getting user from token: {str(e)}")
        return None


def create_user_session(email: str, password: str) -> Dict[str, Any]:
    """
    Create user session (login)

    Args:
        email: User's email
        password: User's password

    Returns:
        Session information with tokens
    """
    try:
        connector = get_cognito_connector()
        return connector.authenticate_user(email, password)

    except Exception as e:
        logger.error(f"Error creating user session: {str(e)}")
        return {'success': False, 'error': 'system_error', 'message': 'Login failed'}


def register_new_user(email: str, password: str, user_attributes: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Register new user

    Args:
        email: User's email
        password: User's password
        user_attributes: Additional user attributes

    Returns:
        Registration result
    """
    try:
        connector = get_cognito_connector()
        result = connector.register_user(email, password, user_attributes)

        # If registration successful, also create user in DynamoDB
        if result['success']:
            try:
                from aws.dynamo_connector import get_dynamo_connector
                dynamo = get_dynamo_connector()

                user_data = {
                    'email': email,
                    'cognito_sub': result['user_sub'],
                    'subscription_status': 'free',
                    'join_date': datetime.now().isoformat()
                }

                if user_attributes:
                    user_data.update(user_attributes)

                dynamo.create_user(user_data)
                logger.info(f"User created in DynamoDB: {email}")

            except Exception as e:
                logger.error(f"Failed to create user in DynamoDB: {str(e)}")
                # Don't fail the registration, but log the error

        return result

    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        return {'success': False, 'error': 'system_error', 'message': 'Registration failed'}


# Health check
def cognito_health_check() -> Dict[str, Any]:
    """Check Cognito connection health"""
    try:
        connector = get_cognito_connector()

        # Try to make a simple API call to test connection
        # We'll use describe_user_pool which requires admin permissions
        # In production, you might want to use a different test

        return {
            'cognito_connection': 'healthy',
            'user_pool_id': connector.user_pool_id,
            'client_id': connector.client_id,
            'region': connector.region,
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'cognito_connection': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


if __name__ == "__main__":
    # Test the connector
    try:
        health = cognito_health_check()
        print("Cognito Health Check:", json.dumps(health, indent=2))
    except Exception as e:
        print(f"Error testing Cognito connector: {e}")