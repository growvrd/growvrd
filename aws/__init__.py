"""
AWS Integration Package for GrowVRD

This package provides all AWS service integrations for the GrowVRD platform,
replacing Google Sheets with enterprise-grade cloud infrastructure.
"""

__version__ = "1.0.0"

# Import main AWS service connectors
try:
    from .dynamo_connector import (
        get_dynamo_connector,
        get_plants_data,
        get_products_data,
        get_kits_data,
        get_users_data,
        get_user_by_email
    )

    from .cognito_auth import (
        get_cognito_connector,
        require_auth,
        require_subscription,
        create_user_session,
        register_new_user
    )

    from .s3_storage import (
        get_s3_manager,
        upload_plant_image,
        upload_user_file,
        get_file_url,
        delete_file
    )

    __all__ = [
        # DynamoDB
        'get_dynamo_connector',
        'get_plants_data',
        'get_products_data',
        'get_kits_data',
        'get_users_data',
        'get_user_by_email',

        # Cognito Auth
        'get_cognito_connector',
        'require_auth',
        'require_subscription',
        'create_user_session',
        'register_new_user',

        # S3 Storage
        'get_s3_manager',
        'upload_plant_image',
        'upload_user_file',
        'get_file_url',
        'delete_file'
    ]

except ImportError as e:
    # Handle import errors gracefully during development
    print(f"Warning: Some AWS modules not available: {e}")
    __all__ = []


def aws_health_check():
    """
    Check health of all AWS services

    Returns:
        Dictionary with health status of all AWS services
    """
    health_status = {
        'timestamp': None,
        'overall_status': 'unknown',
        'services': {}
    }

    try:
        from datetime import datetime
        health_status['timestamp'] = datetime.now().isoformat()

        # Check DynamoDB
        try:
            connector = get_dynamo_connector()
            dynamo_health = connector.health_check()
            health_status['services']['dynamodb'] = dynamo_health
        except Exception as e:
            health_status['services']['dynamodb'] = {'status': 'error', 'error': str(e)}

        # Check S3
        try:
            from .s3_storage import s3_health_check
            s3_health = s3_health_check()
            health_status['services']['s3'] = s3_health
        except Exception as e:
            health_status['services']['s3'] = {'status': 'error', 'error': str(e)}

        # Check Cognito
        try:
            from .cognito_auth import cognito_health_check
            cognito_health = cognito_health_check()
            health_status['services']['cognito'] = cognito_health
        except Exception as e:
            health_status['services']['cognito'] = {'status': 'error', 'error': str(e)}

        # Determine overall status
        all_healthy = all(
            service.get('success') or service.get('cognito_connection') == 'healthy' or service.get(
                'connection') == 'healthy'
            for service in health_status['services'].values()
        )

        health_status['overall_status'] = 'healthy' if all_healthy else 'degraded'

    except Exception as e:
        health_status['overall_status'] = 'error'
        health_status['error'] = str(e)

    return health_status