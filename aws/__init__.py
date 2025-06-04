"""
GrowVRD AWS Integration Package

This package contains AWS infrastructure components for GrowVRD including:
- DynamoDB database operations
- S3 file storage management
- Cognito user authentication
- Lambda serverless functions
- Migration utilities

All components are designed to replace the current Google Sheets and Replit
infrastructure with scalable AWS services.
"""

__version__ = "1.0.0"
__author__ = "GrowVRD Team"

# Import main AWS components for easy access
try:
    from .dynamo_connector import DynamoConnector
    from .s3_storage import S3Storage
    from .cognito_auth import CognitoAuth

    __all__ = [
        'DynamoConnector',
        'S3Storage',
        'CognitoAuth'
    ]
except ImportError as e:
    # Handle import errors gracefully during development
    print(f"Warning: Some AWS modules not available: {e}")
    __all__ = []


def get_aws_config():
    """Get AWS configuration information"""
    import os

    return {
        "region": os.getenv("AWS_REGION", "us-east-1"),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "project_name": os.getenv("PROJECT_NAME", "growvrd"),
        "tables": {
            "plants": os.getenv("DYNAMODB_PLANTS_TABLE"),
            "products": os.getenv("DYNAMODB_PRODUCTS_TABLE"),
            "kits": os.getenv("DYNAMODB_KITS_TABLE"),
            "users": os.getenv("DYNAMODB_USERS_TABLE"),
            "plant_products": os.getenv("DYNAMODB_PLANT_PRODUCTS_TABLE"),
            "user_plants": os.getenv("DYNAMODB_USER_PLANTS_TABLE"),
            "local_vendors": os.getenv("DYNAMODB_LOCAL_VENDORS_TABLE")
        },
        "s3_bucket": os.getenv("S3_BUCKET"),
        "cognito": {
            "user_pool_id": os.getenv("COGNITO_USER_POOL_ID"),
            "client_id": os.getenv("COGNITO_CLIENT_ID")
        }
    }


def health_check():
    """Perform basic health check of AWS components"""
    config = get_aws_config()
    health_status = {
        "aws_configured": True,
        "region": config["region"],
        "environment": config["environment"],
        "components": {
            "dynamodb": bool(config["tables"]["plants"]),
            "s3": bool(config["s3_bucket"]),
            "cognito": bool(config["cognito"]["user_pool_id"])
        },
        "issues": []
    }

    # Check for missing configuration
    if not config["tables"]["plants"]:
        health_status["issues"].append("DynamoDB tables not configured")

    if not config["s3_bucket"]:
        health_status["issues"].append("S3 bucket not configured")

    if not config["cognito"]["user_pool_id"]:
        health_status["issues"].append("Cognito User Pool not configured")

    health_status["healthy"] = len(health_status["issues"]) == 0

    return health_status


def validate_migration_readiness():
    """Check if system is ready for AWS migration"""
    import boto3
    from botocore.exceptions import NoCredentialsError, ClientError

    readiness = {
        "ready": False,
        "aws_credentials": False,
        "aws_permissions": False,
        "required_services": {
            "dynamodb": False,
            "s3": False,
            "cognito": False,
            "lambda": False,
            "iam": False
        },
        "issues": []
    }

    try:
        # Test AWS credentials
        session = boto3.Session()
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        readiness["aws_credentials"] = True
        readiness["account_id"] = identity["Account"]

        # Test basic service access
        services_to_test = ["dynamodb", "s3", "cognito-idp", "lambda", "iam"]

        for service in services_to_test:
            try:
                client = session.client(service)
                # Simple operation to test permissions
                if service == "dynamodb":
                    client.list_tables()
                elif service == "s3":
                    client.list_buckets()
                elif service == "cognito-idp":
                    client.list_user_pools(MaxResults=1)
                elif service == "lambda":
                    client.list_functions(MaxItems=1)
                elif service == "iam":
                    client.list_roles(MaxItems=1)

                service_key = service.replace("-idp", "").replace("-", "_")
                readiness["required_services"][service_key] = True

            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in ['AccessDenied', 'UnauthorizedOperation']:
                    readiness["issues"].append(f"Insufficient permissions for {service}")
                else:
                    readiness["issues"].append(f"Error accessing {service}: {error_code}")
            except Exception as e:
                readiness["issues"].append(f"Error testing {service}: {str(e)}")

        # Check if all required services are accessible
        all_services_ready = all(readiness["required_services"].values())
        readiness["aws_permissions"] = all_services_ready

        # Overall readiness
        readiness["ready"] = (
                readiness["aws_credentials"] and
                readiness["aws_permissions"] and
                len(readiness["issues"]) == 0
        )

    except NoCredentialsError:
        readiness["issues"].append("AWS credentials not found")
    except Exception as e:
        readiness["issues"].append(f"AWS validation error: {str(e)}")

    return readiness


# Print startup info when package is imported
if __name__ != "__main__":
    import os

    if os.getenv("ENVIRONMENT") == "development":
        health = health_check()
        if not health["healthy"]:
            print(f"⚠️  AWS package health: {len(health['issues'])} configuration issues found")
            for issue in health["issues"][:3]:  # Show first 3 issues
                print(f"   - {issue}")