"""
Standardized API response formats for GrowVRD API.

This module provides consistent response formatting for all API endpoints,
including standard error handling, pagination, and metadata.
"""
import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime
from http import HTTPStatus

# Set up logging
logger = logging.getLogger('api_response')

# Constants for response types
RESPONSE_TYPE_SUCCESS = "success"
RESPONSE_TYPE_ERROR = "error"
RESPONSE_TYPE_WARNING = "warning"

# Error codes
ERROR_INVALID_INPUT = "invalid_input"
ERROR_AUTHENTICATION = "authentication_error"
ERROR_AUTHORIZATION = "authorization_error"
ERROR_NOT_FOUND = "not_found"
ERROR_RATE_LIMIT = "rate_limit_exceeded"
ERROR_SERVER = "server_error"
ERROR_DATA_ERROR = "data_error"
ERROR_QUOTA_EXCEEDED = "quota_exceeded"
ERROR_VALIDATION = "validation_error"
ERROR_DEPENDENCY = "dependency_error"


class APIResponse:
    """Class for creating standardized API responses"""

    @staticmethod
    def success(data: Any, message: str = "Success", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a successful API response with standard format.

        Args:
            data: Main response data
            message: Optional success message
            metadata: Optional metadata dictionary

        Returns:
            Dictionary containing the standard response format
        """
        response = {
            "status": RESPONSE_TYPE_SUCCESS,
            "code": HTTPStatus.OK.value,
            "message": message,
            "data": data,
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat()
        }

        # Add metadata if provided
        if metadata:
            response["metadata"] = metadata

        return response

    @staticmethod
    def error(
            message: str,
            error_code: str = ERROR_SERVER,
            http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR.value,
            details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an error API response with standard format.

        Args:
            message: Error message
            error_code: Error code for categorization
            http_status: HTTP status code
            details: Optional additional error details

        Returns:
            Dictionary containing the standard error response format
        """
        response = {
            "status": RESPONSE_TYPE_ERROR,
            "code": http_status,
            "message": message,
            "error": {
                "code": error_code,
                "message": message
            },
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat()
        }

        # Add details if provided
        if details:
            response["error"]["details"] = details

        # Log errors for monitoring
        logger.error(f"API Error: {error_code} - {message} - Details: {details}")

        return response

    @staticmethod
    def warning(
            message: str,
            data: Any = None,
            warning_code: str = "warning",
            details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a warning API response with standard format.

        Args:
            message: Warning message
            data: Optional response data
            warning_code: Warning code for categorization
            details: Optional additional warning details

        Returns:
            Dictionary containing the standard warning response format
        """
        response = {
            "status": RESPONSE_TYPE_WARNING,
            "code": HTTPStatus.OK.value,
            "message": message,
            "warning": {
                "code": warning_code,
                "message": message
            },
            "data": data,
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat()
        }

        # Add details if provided
        if details:
            response["warning"]["details"] = details

        # Log warnings for monitoring
        logger.warning(f"API Warning: {warning_code} - {message}")

        return response

    @staticmethod
    def paginated(
            items: List[Any],
            total_items: int,
            page: int,
            page_size: int,
            message: str = "Success",
            metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a paginated API response with standard format.

        Args:
            items: List of items for current page
            total_items: Total number of items across all pages
            page: Current page number (1-indexed)
            page_size: Number of items per page
            message: Optional success message
            metadata: Optional metadata dictionary

        Returns:
            Dictionary containing the standard paginated response format
        """
        # Calculate pagination values
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)

        pagination = {
            "page": current_page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": current_page < total_pages,
            "has_prev": current_page > 1
        }

        response = {
            "status": RESPONSE_TYPE_SUCCESS,
            "code": HTTPStatus.OK.value,
            "message": message,
            "data": items,
            "pagination": pagination,
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat()
        }

        # Add metadata if provided
        if metadata:
            response["metadata"] = metadata

        return response

    @staticmethod
    def not_found(
            message: str = "Resource not found",
            error_code: str = ERROR_NOT_FOUND,
            resource_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a not found error response with standard format.

        Args:
            message: Error message
            error_code: Error code for categorization
            resource_type: Optional type of resource that was not found

        Returns:
            Dictionary containing the standard not found response format
        """
        details = {"resource_type": resource_type} if resource_type else None

        return APIResponse.error(
            message=message,
            error_code=error_code,
            http_status=HTTPStatus.NOT_FOUND.value,
            details=details
        )

    @staticmethod
    def validation_error(
            message: str = "Validation error",
            validation_errors: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Create a validation error response with standard format.

        Args:
            message: Error message
            validation_errors: Dictionary mapping field names to error messages

        Returns:
            Dictionary containing the standard validation error response format
        """
        details = {
            "validation_errors": validation_errors or {}
        }

        return APIResponse.error(
            message=message,
            error_code=ERROR_VALIDATION,
            http_status=HTTPStatus.BAD_REQUEST.value,
            details=details
        )

    @staticmethod
    def authentication_error(
            message: str = "Authentication required",
            details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an authentication error response with standard format.

        Args:
            message: Error message
            details: Optional additional error details

        Returns:
            Dictionary containing the standard authentication error response format
        """
        return APIResponse.error(
            message=message,
            error_code=ERROR_AUTHENTICATION,
            http_status=HTTPStatus.UNAUTHORIZED.value,
            details=details
        )

    @staticmethod
    def authorization_error(
            message: str = "Not authorized",
            details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an authorization error response with standard format.

        Args:
            message: Error message
            details: Optional additional error details

        Returns:
            Dictionary containing the standard authorization error response format
        """
        return APIResponse.error(
            message=message,
            error_code=ERROR_AUTHORIZATION,
            http_status=HTTPStatus.FORBIDDEN.value,
            details=details
        )

    @staticmethod
    def rate_limit_error(
            message: str = "Rate limit exceeded",
            retry_after: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a rate limit error response with standard format.

        Args:
            message: Error message
            retry_after: Optional seconds to wait before retrying

        Returns:
            Dictionary containing the standard rate limit error response format
        """
        details = {"retry_after": retry_after} if retry_after else None

        return APIResponse.error(
            message=message,
            error_code=ERROR_RATE_LIMIT,
            http_status=HTTPStatus.TOO_MANY_REQUESTS.value,
            details=details
        )

    @staticmethod
    def quota_exceeded_error(
            message: str = "Quota exceeded",
            quota_reset: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a quota exceeded error response with standard format.

        Args:
            message: Error message
            quota_reset: Optional date/time when quota resets

        Returns:
            Dictionary containing the standard quota exceeded error response format
        """
        details = {"quota_reset": quota_reset} if quota_reset else None

        return APIResponse.error(
            message=message,
            error_code=ERROR_QUOTA_EXCEEDED,
            http_status=HTTPStatus.FORBIDDEN.value,
            details=details
        )


def handle_exception(e: Exception) -> Dict[str, Any]:
    """
    Convert exceptions to standardized API responses based on exception type.

    Args:
        e: The exception to handle

    Returns:
        Standardized API error response
    """
    # Import exception types here to avoid circular imports
    from core.recommendation_engine import (
        InvalidPreferenceError, DataRetrievalError, QuotaExceededError
    )
    from core.oauth_sheets_connector import (
        GoogleSheetsConnectionError, GoogleSheetsDataError
    )

    # Map exception types to appropriate responses
    if isinstance(e, InvalidPreferenceError):
        return APIResponse.validation_error(
            message=str(e),
            validation_errors={"preferences": str(e)}
        )
    elif isinstance(e, DataRetrievalError) or isinstance(e, GoogleSheetsDataError):
        return APIResponse.error(
            message=f"Data retrieval error: {str(e)}",
            error_code=ERROR_DATA_ERROR,
            http_status=HTTPStatus.SERVICE_UNAVAILABLE.value
        )
    elif isinstance(e, QuotaExceededError):
        return APIResponse.quota_exceeded_error(
            message=str(e),
            quota_reset="24 hours from now"  # This should be calculated dynamically
        )
    elif isinstance(e, GoogleSheetsConnectionError):
        return APIResponse.error(
            message=f"Database connection error: {str(e)}",
            error_code=ERROR_DEPENDENCY,
            http_status=HTTPStatus.SERVICE_UNAVAILABLE.value
        )
    else:
        # Handle unexpected exceptions
        logger.exception("Unhandled exception")
        return APIResponse.error(
            message="An unexpected error occurred",
            error_code=ERROR_SERVER,
            http_status=HTTPStatus.INTERNAL_SERVER_ERROR.value,
            details={"exception_type": type(e).__name__}
        )


# Performance monitoring functions
_request_start_times = {}


def start_request_timing(request_id: str) -> None:
    """
    Start timing a request for performance monitoring.

    Args:
        request_id: Unique request identifier
    """
    _request_start_times[request_id] = time.time()


def end_request_timing(request_id: str) -> Optional[float]:
    """
    End timing a request and return the duration.

    Args:
        request_id: Unique request identifier

    Returns:
        Request duration in seconds, or None if request_id not found
    """
    if request_id in _request_start_times:
        duration = time.time() - _request_start_times[request_id]
        del _request_start_times[request_id]
        return duration
    return None


# Flask integration helper functions
def with_standard_response(func):
    """
    Decorator to wrap Flask route handlers with standardized response formatting.

    Args:
        func: Flask route handler function

    Returns:
        Wrapped function that returns standardized responses
    """
    import functools
    from flask import jsonify

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        request_id = str(uuid.uuid4())
        start_request_timing(request_id)

        try:
            # Call the original function
            result = func(*args, **kwargs)

            # If result is already a dict and has a 'status' field, assume it's already formatted
            if isinstance(result, dict) and 'status' in result:
                # Add timing metadata
                duration = end_request_timing(request_id)
                if duration is not None and 'metadata' not in result:
                    result['metadata'] = {'duration': f"{duration:.4f}s"}
                elif duration is not None and 'metadata' in result:
                    result['metadata']['duration'] = f"{duration:.4f}s"

                # If the request_id is missing, add it
                if 'request_id' not in result:
                    result['request_id'] = request_id

                return jsonify(result)

            # Otherwise, format as a success response
            duration = end_request_timing(request_id)
            metadata = {'duration': f"{duration:.4f}s"} if duration is not None else None

            response = APIResponse.success(result, metadata=metadata)
            response['request_id'] = request_id

            return jsonify(response)

        except Exception as e:
            # End timing and handle exception
            duration = end_request_timing(request_id)
            error_response = handle_exception(e)

            # Add timing metadata
            if duration is not None and 'metadata' not in error_response:
                error_response['metadata'] = {'duration': f"{duration:.4f}s"}
            elif duration is not None and 'metadata' in error_response:
                error_response['metadata']['duration'] = f"{duration:.4f}s"

            # Ensure request_id is present
            error_response['request_id'] = request_id

            return jsonify(error_response), error_response['code']

    return wrapper