"""
Health Check Lambda Function for GrowVRD

This Lambda function provides comprehensive health monitoring for the GrowVRD system,
checking all AWS services and dependencies to ensure the platform is running correctly.
"""

import json
import boto3
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
cognito = boto3.client('cognito-idp')
lambda_client = boto3.client('lambda')

# Configuration from environment variables
import os

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
PROJECT_NAME = os.getenv('PROJECT_NAME', 'growvrd')

# Table and resource names
DYNAMODB_TABLES = {
    'plants': os.getenv('DYNAMODB_PLANTS_TABLE', f'{PROJECT_NAME}-plants-{ENVIRONMENT}'),
    'products': os.getenv('DYNAMODB_PRODUCTS_TABLE', f'{PROJECT_NAME}-products-{ENVIRONMENT}'),
    'kits': os.getenv('DYNAMODB_KITS_TABLE', f'{PROJECT_NAME}-kits-{ENVIRONMENT}'),
    'users': os.getenv('DYNAMODB_USERS_TABLE', f'{PROJECT_NAME}-users-{ENVIRONMENT}'),
    'plant_products': os.getenv('DYNAMODB_PLANT_PRODUCTS_TABLE', f'{PROJECT_NAME}-plant-products-{ENVIRONMENT}'),
    'user_plants': os.getenv('DYNAMODB_USER_PLANTS_TABLE', f'{PROJECT_NAME}-user-plants-{ENVIRONMENT}'),
    'local_vendors': os.getenv('DYNAMODB_LOCAL_VENDORS_TABLE', f'{PROJECT_NAME}-local-vendors-{ENVIRONMENT}')
}

S3_BUCKET = os.getenv('S3_BUCKET', f'{PROJECT_NAME}-storage-{ENVIRONMENT}')
COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
LAMBDA_FUNCTIONS = {
    'recommendation': os.getenv('LAMBDA_RECOMMENDATION_ARN'),
    'user_management': os.getenv('LAMBDA_USER_MANAGEMENT_ARN')
}


def lambda_handler(event, context):
    """
    Main Lambda handler for health checks.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        JSON response with health status
    """
    try:
        start_time = time.time()

        # Parse request
        check_type = event.get('check_type', 'comprehensive')
        include_performance = event.get('include_performance', True)

        logger.info(f"Starting {check_type} health check")

        # Perform health checks based on type
        if check_type == 'quick':
            health_data = perform_quick_health_check()
        elif check_type == 'database':
            health_data = perform_database_health_check()
        elif check_type == 'services':
            health_data = perform_services_health_check()
        else:  # comprehensive
            health_data = perform_comprehensive_health_check()

        # Add performance metrics if requested
        if include_performance:
            health_data['performance'] = get_performance_metrics()

        # Calculate total execution time
        execution_time = time.time() - start_time
        health_data['execution_time_ms'] = round(execution_time * 1000, 2)

        # Determine overall health status
        overall_status = determine_overall_health(health_data)
        health_data['overall_status'] = overall_status
        health_data['timestamp'] = datetime.utcnow().isoformat() + 'Z'

        # Log results
        logger.info(f"Health check completed in {execution_time:.3f}s - Status: {overall_status}")

        return {
            'statusCode': 200 if overall_status == 'healthy' else 503,
            'headers': {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            'body': json.dumps(health_data, default=str)
        }

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'overall_status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }


def perform_quick_health_check() -> Dict[str, Any]:
    """
    Perform a quick health check of critical services.

    Returns:
        Dictionary with quick health check results
    """
    health_data = {
        'check_type': 'quick',
        'services': {}
    }

    # Check Lambda function itself
    health_data['services']['lambda'] = {
        'status': 'healthy',
        'message': 'Lambda function executing successfully'
    }

    # Quick DynamoDB check - just check if one table exists
    try:
        table_name = DYNAMODB_TABLES['plants']
        response = dynamodb.describe_table(TableName=table_name)
        status = response['Table']['TableStatus']

        health_data['services']['dynamodb'] = {
            'status': 'healthy' if status == 'ACTIVE' else 'degraded',
            'message': f"Primary table status: {status}",
            'checked_table': table_name
        }
    except Exception as e:
        health_data['services']['dynamodb'] = {
            'status': 'unhealthy',
            'message': f"DynamoDB check failed: {str(e)}"
        }

    # Quick S3 check
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        health_data['services']['s3'] = {
            'status': 'healthy',
            'message': f"S3 bucket {S3_BUCKET} accessible"
        }
    except Exception as e:
        health_data['services']['s3'] = {
            'status': 'unhealthy',
            'message': f"S3 check failed: {str(e)}"
        }

    return health_data


def perform_database_health_check() -> Dict[str, Any]:
    """
    Perform comprehensive database health checks.

    Returns:
        Dictionary with database health check results
    """
    health_data = {
        'check_type': 'database',
        'services': {
            'dynamodb': {
                'tables': {},
                'overall_status': 'healthy'
            }
        }
    }

    unhealthy_tables = 0

    for table_type, table_name in DYNAMODB_TABLES.items():
        try:
            response = dynamodb.describe_table(TableName=table_name)
            table_info = response['Table']

            # Get table metrics
            item_count = table_info.get('ItemCount', 0)
            table_size = table_info.get('TableSizeBytes', 0)
            table_status = table_info['TableStatus']

            # Check if table is active and accessible
            if table_status == 'ACTIVE':
                # Test read access
                scan_response = dynamodb.scan(
                    TableName=table_name,
                    Limit=1
                )

                health_data['services']['dynamodb']['tables'][table_type] = {
                    'status': 'healthy',
                    'table_name': table_name,
                    'table_status': table_status,
                    'item_count': item_count,
                    'size_bytes': table_size,
                    'read_test': 'passed'
                }
            else:
                health_data['services']['dynamodb']['tables'][table_type] = {
                    'status': 'degraded',
                    'table_name': table_name,
                    'table_status': table_status,
                    'message': f"Table not active: {table_status}"
                }
                unhealthy_tables += 1

        except Exception as e:
            health_data['services']['dynamodb']['tables'][table_type] = {
                'status': 'unhealthy',
                'table_name': table_name,
                'error': str(e)
            }
            unhealthy_tables += 1

    # Set overall DynamoDB status
    if unhealthy_tables == 0:
        health_data['services']['dynamodb']['overall_status'] = 'healthy'
    elif unhealthy_tables < len(DYNAMODB_TABLES) / 2:
        health_data['services']['dynamodb']['overall_status'] = 'degraded'
    else:
        health_data['services']['dynamodb']['overall_status'] = 'unhealthy'

    health_data['services']['dynamodb']['summary'] = {
        'total_tables': len(DYNAMODB_TABLES),
        'healthy_tables': len(DYNAMODB_TABLES) - unhealthy_tables,
        'unhealthy_tables': unhealthy_tables
    }

    return health_data


def perform_services_health_check() -> Dict[str, Any]:
    """
    Perform health checks on all AWS services.

    Returns:
        Dictionary with services health check results
    """
    health_data = {
        'check_type': 'services',
        'services': {}
    }

    # S3 Health Check
    health_data['services']['s3'] = check_s3_health()

    # Cognito Health Check
    health_data['services']['cognito'] = check_cognito_health()

    # Lambda Functions Health Check
    health_data['services']['lambda_functions'] = check_lambda_functions_health()

    return health_data


def perform_comprehensive_health_check() -> Dict[str, Any]:
    """
    Perform comprehensive health checks on all components.

    Returns:
        Dictionary with comprehensive health check results
    """
    health_data = {
        'check_type': 'comprehensive',
        'services': {}
    }

    # Combine all health checks
    db_health = perform_database_health_check()
    services_health = perform_services_health_check()

    # Merge results
    health_data['services'].update(db_health['services'])
    health_data['services'].update(services_health['services'])

    # Add system information
    health_data['system'] = get_system_information()

    # Add dependency checks
    health_data['dependencies'] = check_external_dependencies()

    return health_data


def check_s3_health() -> Dict[str, Any]:
    """Check S3 bucket health and accessibility."""
    try:
        # Check bucket exists and is accessible
        s3.head_bucket(Bucket=S3_BUCKET)

        # Test upload/download capability
        test_key = f"health-check/{datetime.utcnow().isoformat()}.txt"
        test_content = "GrowVRD health check test file"

        # Upload test file
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=test_key,
            Body=test_content.encode('utf-8'),
            ContentType='text/plain'
        )

        # Download test file
        response = s3.get_object(Bucket=S3_BUCKET, Key=test_key)
        downloaded_content = response['Body'].read().decode('utf-8')

        # Clean up test file
        s3.delete_object(Bucket=S3_BUCKET, Key=test_key)

        # Verify content
        if downloaded_content == test_content:
            return {
                'status': 'healthy',
                'bucket': S3_BUCKET,
                'read_test': 'passed',
                'write_test': 'passed',
                'delete_test': 'passed'
            }
        else:
            return {
                'status': 'degraded',
                'bucket': S3_BUCKET,
                'message': 'Content verification failed'
            }

    except Exception as e:
        return {
            'status': 'unhealthy',
            'bucket': S3_BUCKET,
            'error': str(e)
        }


def check_cognito_health() -> Dict[str, Any]:
    """Check Cognito User Pool health."""
    if not COGNITO_USER_POOL_ID:
        return {
            'status': 'not_configured',
            'message': 'Cognito User Pool ID not provided'
        }

    try:
        # Describe user pool
        response = cognito.describe_user_pool(UserPoolId=COGNITO_USER_POOL_ID)
        user_pool = response['UserPool']

        # Get user pool statistics
        try:
            stats_response = cognito.list_users(UserPoolId=COGNITO_USER_POOL_ID, Limit=1)
            user_count_available = True
        except:
            user_count_available = False

        return {
            'status': 'healthy',
            'user_pool_id': COGNITO_USER_POOL_ID,
            'user_pool_name': user_pool['Name'],
            'status_detail': user_pool.get('Status', 'UNKNOWN'),
            'creation_date': user_pool.get('CreationDate'),
            'user_count_available': user_count_available
        }

    except Exception as e:
        return {
            'status': 'unhealthy',
            'user_pool_id': COGNITO_USER_POOL_ID,
            'error': str(e)
        }


def check_lambda_functions_health() -> Dict[str, Any]:
    """Check health of other Lambda functions."""
    lambda_health = {
        'functions': {},
        'overall_status': 'healthy'
    }

    unhealthy_functions = 0

    for func_name, func_arn in LAMBDA_FUNCTIONS.items():
        if not func_arn:
            lambda_health['functions'][func_name] = {
                'status': 'not_configured',
                'message': 'Function ARN not provided'
            }
            continue

        try:
            # Extract function name from ARN
            function_name = func_arn.split(':')[-1]

            # Get function configuration
            response = lambda_client.get_function(FunctionName=function_name)
            config = response['Configuration']

            # Test function invocation with a simple health check
            try:
                test_response = lambda_client.invoke(
                    FunctionName=function_name,
                    InvocationType='RequestResponse',
                    Payload=json.dumps({'action': 'health_check'})
                )

                if test_response['StatusCode'] == 200:
                    invocation_status = 'healthy'
                    invocation_message = 'Function invocation successful'
                else:
                    invocation_status = 'degraded'
                    invocation_message = f"Function returned status {test_response['StatusCode']}"
            except:
                invocation_status = 'degraded'
                invocation_message = 'Function invocation test skipped'

            lambda_health['functions'][func_name] = {
                'status': invocation_status,
                'function_name': function_name,
                'state': config['State'],
                'last_modified': config['LastModified'],
                'runtime': config['Runtime'],
                'timeout': config['Timeout'],
                'memory_size': config['MemorySize'],
                'invocation_test': invocation_message
            }

            if invocation_status == 'unhealthy':
                unhealthy_functions += 1

        except Exception as e:
            lambda_health['functions'][func_name] = {
                'status': 'unhealthy',
                'function_arn': func_arn,
                'error': str(e)
            }
            unhealthy_functions += 1

    # Set overall status
    total_functions = len([f for f in LAMBDA_FUNCTIONS.values() if f])
    if total_functions == 0:
        lambda_health['overall_status'] = 'not_configured'
    elif unhealthy_functions == 0:
        lambda_health['overall_status'] = 'healthy'
    elif unhealthy_functions < total_functions / 2:
        lambda_health['overall_status'] = 'degraded'
    else:
        lambda_health['overall_status'] = 'unhealthy'

    return lambda_health


def get_performance_metrics() -> Dict[str, Any]:
    """Get performance metrics for the system."""
    return {
        'lambda_environment': {
            'memory_limit_mb': int(os.getenv('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', 512)),
            'timeout_seconds': int(os.getenv('AWS_LAMBDA_FUNCTION_TIMEOUT', 300)),
            'runtime': os.getenv('AWS_EXECUTION_ENV', 'unknown')
        },
        'response_times': {
            'target_api_response_ms': 300,
            'current_health_check_ms': 'calculated_at_end'
        }
    }


def get_system_information() -> Dict[str, Any]:
    """Get system information and configuration."""
    return {
        'environment': ENVIRONMENT,
        'aws_region': AWS_REGION,
        'project_name': PROJECT_NAME,
        'lambda_version': os.getenv('AWS_LAMBDA_FUNCTION_VERSION', '$LATEST'),
        'python_version': os.getenv('AWS_LAMBDA_RUNTIME_API', 'python3.9'),
        'configured_resources': {
            's3_bucket': S3_BUCKET,
            'cognito_configured': bool(COGNITO_USER_POOL_ID),
            'dynamodb_tables_configured': len(DYNAMODB_TABLES),
            'lambda_functions_configured': len([f for f in LAMBDA_FUNCTIONS.values() if f])
        }
    }


def check_external_dependencies() -> Dict[str, Any]:
    """Check external API dependencies."""
    dependencies = {}

    # Note: We can't easily test OpenAI and Perenual APIs from this Lambda
    # without having the API keys, so we'll just note their configuration status
    dependencies['openai'] = {
        'status': 'not_tested',
        'message': 'OpenAI API key should be configured in main application'
    }

    dependencies['perenual'] = {
        'status': 'not_tested',
        'message': 'Perenual API key should be configured in main application'
    }

    return dependencies


def determine_overall_health(health_data: Dict[str, Any]) -> str:
    """
    Determine overall health status based on individual component health.

    Args:
        health_data: Dictionary containing health check results

    Returns:
        Overall health status: 'healthy', 'degraded', 'unhealthy', or 'error'
    """
    services = health_data.get('services', {})

    if not services:
        return 'error'

    unhealthy_count = 0
    degraded_count = 0
    total_services = 0

    for service_name, service_data in services.items():
        if isinstance(service_data, dict):
            status = service_data.get('status') or service_data.get('overall_status', 'unknown')

            if status in ['unhealthy', 'error']:
                unhealthy_count += 1
            elif status in ['degraded', 'warning']:
                degraded_count += 1

            total_services += 1

    # Determine overall status
    if unhealthy_count > 0:
        if unhealthy_count >= total_services / 2:
            return 'unhealthy'
        else:
            return 'degraded'
    elif degraded_count > 0:
        return 'degraded'
    else:
        return 'healthy'


# For testing locally
if __name__ == "__main__":
    # Test event
    test_event = {
        'check_type': 'comprehensive',
        'include_performance': True
    }


    # Mock context
    class MockContext:
        def __init__(self):
            self.function_name = 'growvrd-health-check-development'
            self.function_version = '1'
            self.memory_limit_in_mb = 512


    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2, default=str))