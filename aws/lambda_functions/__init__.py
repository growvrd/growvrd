"""
GrowVRD Lambda Functions Package

This package contains serverless Lambda functions for GrowVRD including:
- recommendation.py: Core plant recommendation engine
- health_check.py: System health monitoring
- user_management.py: User account operations

These functions provide the serverless backend for GrowVRD's core functionality,
designed to handle high-scale operations with optimal performance.
"""

__version__ = "1.0.0"
__author__ = "GrowVRD Team"

# Lambda function metadata
LAMBDA_FUNCTIONS = {
    "recommendation": {
        "description": "Core plant recommendation engine",
        "handler": "recommendation.lambda_handler",
        "runtime": "python3.9",
        "timeout": 300,
        "memory": 512,
        "environment_variables": [
            "DYNAMODB_PLANTS_TABLE",
            "DYNAMODB_PRODUCTS_TABLE",
            "DYNAMODB_KITS_TABLE",
            "OPENAI_API_KEY",
            "PERENUAL_API_KEY"
        ]
    },
    "health_check": {
        "description": "System health monitoring and diagnostics",
        "handler": "health_check.lambda_handler",
        "runtime": "python3.9",
        "timeout": 120,
        "memory": 256,
        "environment_variables": [
            "DYNAMODB_PLANTS_TABLE",
            "DYNAMODB_PRODUCTS_TABLE",
            "DYNAMODB_KITS_TABLE",
            "DYNAMODB_USERS_TABLE",
            "S3_BUCKET",
            "COGNITO_USER_POOL_ID"
        ]
    },
    "user_management": {
        "description": "User account operations and management",
        "handler": "user_management.lambda_handler",
        "runtime": "python3.9",
        "timeout": 180,
        "memory": 384,
        "environment_variables": [
            "DYNAMODB_USERS_TABLE",
            "COGNITO_USER_POOL_ID",
            "COGNITO_CLIENT_ID"
        ]
    }
}

# Required IAM permissions for Lambda functions
REQUIRED_PERMISSIONS = {
    "dynamodb": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
    ],
    "s3": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
    ],
    "cognito": [
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminUpdateUserAttributes",
        "cognito-idp:ListUsers"
    ],
    "logs": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
    ]
}


def get_lambda_config(function_name: str) -> dict:
    """Get configuration for a specific Lambda function"""
    if function_name not in LAMBDA_FUNCTIONS:
        raise ValueError(f"Unknown Lambda function: {function_name}")

    return LAMBDA_FUNCTIONS[function_name]


def get_all_lambda_configs() -> dict:
    """Get configurations for all Lambda functions"""
    return LAMBDA_FUNCTIONS


def validate_environment_variables(function_name: str) -> dict:
    """Validate required environment variables for a Lambda function"""
    import os

    if function_name not in LAMBDA_FUNCTIONS:
        raise ValueError(f"Unknown Lambda function: {function_name}")

    config = LAMBDA_FUNCTIONS[function_name]
    required_vars = config["environment_variables"]

    validation = {
        "function_name": function_name,
        "all_present": True,
        "missing_variables": [],
        "present_variables": []
    }

    for var in required_vars:
        if os.getenv(var):
            validation["present_variables"].append(var)
        else:
            validation["missing_variables"].append(var)
            validation["all_present"] = False

    return validation


def get_deployment_package_requirements() -> list:
    """Get Python package requirements for Lambda deployment"""
    return [
        "boto3>=1.26.0",
        "botocore>=1.29.0",
        "openai>=1.0.0",
        "requests>=2.28.0",
        "python-dotenv>=1.0.0"
    ]


def create_requirements_txt() -> str:
    """Create requirements.txt content for Lambda functions"""
    requirements = get_deployment_package_requirements()
    return "\n".join(requirements) + "\n"


# Utility functions for Lambda development
def lambda_response(status_code: int, body: dict, headers: dict = None) -> dict:
    """Create standardized Lambda response"""
    if headers is None:
        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        }

    return {
        'statusCode': status_code,
        'headers': headers,
        'body': body if isinstance(body, str) else str(body)
    }


def lambda_error_response(error_message: str, status_code: int = 500) -> dict:
    """Create standardized Lambda error response"""
    import json
    from datetime import datetime

    error_body = {
        'error': True,
        'message': error_message,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

    return lambda_response(status_code, json.dumps(error_body))


def lambda_success_response(data: dict, message: str = "Success") -> dict:
    """Create standardized Lambda success response"""
    import json
    from datetime import datetime

    success_body = {
        'success': True,
        'message': message,
        'data': data,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

    return lambda_response(200, json.dumps(success_body, default=str))


def parse_lambda_event(event: dict) -> dict:
    """Parse and validate Lambda event data"""
    import json

    parsed = {
        'method': event.get('httpMethod', 'POST'),
        'path': event.get('path', '/'),
        'headers': event.get('headers', {}),
        'query_params': event.get('queryStringParameters') or {},
        'path_params': event.get('pathParameters') or {},
        'body': None,
        'is_api_gateway': 'httpMethod' in event
    }

    # Parse body if present
    if event.get('body'):
        try:
            parsed['body'] = json.loads(event['body'])
        except json.JSONDecodeError:
            parsed['body'] = event['body']  # Keep as string if not JSON

    return parsed


def get_lambda_context_info(context) -> dict:
    """Extract useful information from Lambda context"""
    return {
        'function_name': context.function_name,
        'function_version': context.function_version,
        'memory_limit': context.memory_limit_in_mb,
        'request_id': context.aws_request_id,
        'remaining_time_ms': context.get_remaining_time_in_millis()
    }


# Export main utilities
__all__ = [
    'LAMBDA_FUNCTIONS',
    'REQUIRED_PERMISSIONS',
    'get_lambda_config',
    'get_all_lambda_configs',
    'validate_environment_variables',
    'get_deployment_package_requirements',
    'create_requirements_txt',
    'lambda_response',
    'lambda_error_response',
    'lambda_success_response',
    'parse_lambda_event',
    'get_lambda_context_info'
]