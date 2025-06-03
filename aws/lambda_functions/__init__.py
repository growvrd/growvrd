"""
AWS Lambda Functions Package for GrowVRD

This package contains all serverless Lambda functions for the GrowVRD platform.
Each function is optimized for performance and automatic scaling.
"""

__version__ = "1.0.0"

# Import main handler functions for easy access
try:
    from .recommendation import lambda_handler as recommendation_handler
    from .health_check import lambda_handler as health_check_handler
    from .user_management import lambda_handler as user_management_handler

    __all__ = [
        'recommendation_handler',
        'health_check_handler',
        'user_management_handler'
    ]
except ImportError as e:
    # Handle import errors gracefully during development
    print(f"Warning: Some Lambda functions not available: {e}")
    __all__ = []

# Lambda function registry for deployment
LAMBDA_FUNCTIONS = {
    'growvrd-recommendation': {
        'handler': 'recommendation.lambda_handler',
        'description': 'Plant recommendation engine',
        'timeout': 30,
        'memory': 512
    },
    'growvrd-health-check': {
        'handler': 'health_check.lambda_handler',
        'description': 'System health monitoring',
        'timeout': 10,
        'memory': 128
    },
    'growvrd-user-management': {
        'handler': 'user_management.lambda_handler',
        'description': 'User account management',
        'timeout': 15,
        'memory': 256
    }
}