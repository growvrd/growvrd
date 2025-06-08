import boto3
import json
import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('aws_migration')


class AWSMigrationManager:
    """Manages the complete migration of GrowVRD from Google Sheets to AWS."""

    def __init__(self, aws_region: str = 'us-east-1', environment: str = 'development'):
        """
        Initialize AWS Migration Manager.

        Args:
            aws_region: AWS region to deploy resources
            environment: Environment name (development, staging, production)
        """
        # Load .env file if not already loaded
        if not os.getenv('AWS_ACCESS_KEY_ID'):
            load_dotenv()

        self.region = aws_region
        self.environment = environment
        self.project_name = 'growvrd'

        # Get AWS credentials from environment
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region_env = os.getenv('AWS_DEFAULT_REGION', aws_region)

        if not aws_access_key or not aws_secret_key:
            logger.error("AWS credentials not found in environment variables or .env file")
            logger.error("Please ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set in your .env file")
            raise ValueError("Missing AWS credentials")

        # Initialize AWS clients with explicit credentials
        self.session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region_env
        )
        self.dynamodb = self.session.client('dynamodb')
        self.s3 = self.session.client('s3')
        self.cognito = self.session.client('cognito-idp')
        self.lambda_client = self.session.client('lambda')
        self.iam = self.session.client('iam')

    def validate_aws_credentials(self) -> bool:
        """Validate AWS credentials and permissions."""
        try:
            # Test credentials with STS
            sts = self.session.client('sts')
            identity = sts.get_caller_identity()
            logger.info(f"AWS credentials validated for account: {identity['Account']}")
            return True
        except Exception as e:
            logger.error(f"AWS credentials validation failed: {str(e)}")
            return False

    def create_s3_bucket(self) -> str:
        """
        Create S3 bucket for file storage.

        Returns:
            S3 bucket name
        """
        bucket_name = f"{self.project_name}-storage-{self.environment}"

        try:
            # Check if bucket exists
            try:
                self.s3.head_bucket(Bucket=bucket_name)
                logger.info(f"S3 bucket {bucket_name} already exists")
                return bucket_name
            except self.s3.exceptions.NoSuchBucket:
                pass

            # Create bucket
            if self.region == 'us-east-1':
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )

            # Configure bucket for web access
            self.s3.put_bucket_cors(
                Bucket=bucket_name,
                CORSConfiguration={
                    'CORSRules': [
                        {
                            'AllowedHeaders': ['*'],
                            'AllowedMethods': ['GET', 'PUT', 'POST'],
                            'AllowedOrigins': ['*'],
                            'MaxAgeSeconds': 3000
                        }
                    ]
                }
            )

            logger.info(f"Created S3 bucket: {bucket_name}")
            return bucket_name

        except Exception as e:
            logger.error(f"Failed to create S3 bucket: {str(e)}")
            raise

    def create_dynamodb_tables(self) -> Dict[str, str]:
        """
        Create all DynamoDB tables for GrowVRD.

        Returns:
            Dictionary mapping table purposes to table names
        """
        tables = {
            'plants': f"{self.project_name}-plants-{self.environment}",
            'products': f"{self.project_name}-products-{self.environment}",
            'kits': f"{self.project_name}-kits-{self.environment}",
            'users': f"{self.project_name}-users-{self.environment}",
            'plant_products': f"{self.project_name}-plant-products-{self.environment}",
            'user_plants': f"{self.project_name}-user-plants-{self.environment}",
            'local_vendors': f"{self.project_name}-local-vendors-{self.environment}"
        }

        table_definitions = {
            'plants': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'name', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'name-index',
                        'KeySchema': [{'AttributeName': 'name', 'KeyType': 'HASH'}],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            'products': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'category', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'category-index',
                        'KeySchema': [{'AttributeName': 'category', 'KeyType': 'HASH'}],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            'kits': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            'users': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'email', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'email-index',
                        'KeySchema': [{'AttributeName': 'email', 'KeyType': 'HASH'}],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            'plant_products': {
                'AttributeDefinitions': [
                    {'AttributeName': 'plant_id', 'AttributeType': 'S'},
                    {'AttributeName': 'product_id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'plant_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'product_id', 'KeyType': 'RANGE'}
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            'user_plants': {
                'AttributeDefinitions': [
                    {'AttributeName': 'user_id', 'AttributeType': 'S'},
                    {'AttributeName': 'plant_id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'plant_id', 'KeyType': 'RANGE'}
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            'local_vendors': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'location', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'location-index',
                        'KeySchema': [{'AttributeName': 'location', 'KeyType': 'HASH'}],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            }
        }

        created_tables = {}

        for table_type, table_name in tables.items():
            try:
                # Check if table already exists
                try:
                    self.dynamodb.describe_table(TableName=table_name)
                    logger.info(f"DynamoDB table {table_name} already exists")
                    created_tables[table_type] = table_name
                    continue
                except self.dynamodb.exceptions.ResourceNotFoundException:
                    pass

                # Create table
                table_config = table_definitions[table_type].copy()
                table_config['TableName'] = table_name

                self.dynamodb.create_table(**table_config)

                # Wait for table to be active
                waiter = self.dynamodb.get_waiter('table_exists')
                waiter.wait(TableName=table_name)

                logger.info(f"Created DynamoDB table: {table_name}")
                created_tables[table_type] = table_name

            except Exception as e:
                logger.error(f"Failed to create table {table_name}: {str(e)}")
                raise

        return created_tables

    def create_cognito_user_pool(self) -> Dict[str, str]:
        """
        Create Cognito User Pool for authentication.

        Returns:
            Dictionary with user pool configuration
        """
        try:
            user_pool_name = f"{self.project_name}-users-{self.environment}"

            # Create user pool
            response = self.cognito.create_user_pool(
                PoolName=user_pool_name,
                Policies={
                    'PasswordPolicy': {
                        'MinimumLength': 8,
                        'RequireUppercase': True,
                        'RequireLowercase': True,
                        'RequireNumbers': True,
                        'RequireSymbols': False
                    }
                },
                AutoVerifiedAttributes=['email'],
                Schema=[
                    {
                        'Name': 'email',
                        'AttributeDataType': 'String',
                        'Required': True,
                        'Mutable': True
                    }
                ]
            )

            user_pool_id = response['UserPool']['Id']

            # Create user pool client
            client_response = self.cognito.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName=f"{self.project_name}-client-{self.environment}",
                GenerateSecret=False,
                ExplicitAuthFlows=[
                    'ADMIN_NO_SRP_AUTH',
                    'USER_PASSWORD_AUTH'
                ]
            )

            client_id = client_response['UserPoolClient']['ClientId']

            logger.info(f"Created Cognito User Pool: {user_pool_id}")
            logger.info(f"Created Cognito Client: {client_id}")

            return {
                'user_pool_id': user_pool_id,
                'client_id': client_id
            }

        except Exception as e:
            logger.error(f"Failed to create Cognito user pool: {str(e)}")
            raise

    def create_lambda_execution_role(self) -> str:
        """
        Create IAM role for Lambda functions.

        Returns:
            IAM role ARN
        """
        try:
            role_name = f"{self.project_name}-lambda-role-{self.environment}"

            # Check if role already exists
            try:
                response = self.iam.get_role(RoleName=role_name)
                logger.info(f"IAM role {role_name} already exists")
                return response['Role']['Arn']
            except self.iam.exceptions.NoSuchEntityException:
                pass

            # Create role
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }

            response = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Execution role for {self.project_name} Lambda functions"
            )

            role_arn = response['Role']['Arn']

            # Attach basic Lambda execution policy
            self.iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
            )

            # Attach DynamoDB access policy
            self.iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess'
            )

            logger.info(f"Created IAM role: {role_arn}")
            return role_arn

        except Exception as e:
            logger.error(f"Failed to create Lambda execution role: {str(e)}")
            raise

    def deploy_lambda_functions(self, role_arn: str) -> Dict[str, str]:
        """
        Deploy Lambda functions for GrowVRD.

        Args:
            role_arn: IAM role ARN for Lambda execution

        Returns:
            Dictionary mapping function purposes to ARNs
        """
        # For now, we'll create placeholder functions
        # In a real implementation, you'd package and deploy your actual functions

        functions = {
            'recommendation': f"{self.project_name}-recommendation-{self.environment}",
            'health_check': f"{self.project_name}-health-check-{self.environment}",
            'user_management': f"{self.project_name}-user-management-{self.environment}"
        }

        deployed_functions = {}

        # Basic Lambda function code
        basic_function_code = '''
import json

def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Function deployed successfully'})
    }
'''

        for function_type, function_name in functions.items():
            try:
                # Check if function already exists
                try:
                    response = self.lambda_client.get_function(FunctionName=function_name)
                    logger.info(f"Lambda function {function_name} already exists")
                    deployed_functions[function_type] = response['Configuration']['FunctionArn']
                    continue
                except self.lambda_client.exceptions.ResourceNotFoundException:
                    pass

                # Create a proper zip file for the Lambda function
                import zipfile
                import io

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.writestr('lambda_function.py', basic_function_code)

                zip_buffer.seek(0)
                zip_content = zip_buffer.read()

                # Create function
                response = self.lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime='python3.9',
                    Role=role_arn,
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': zip_content},
                    Description=f"GrowVRD {function_type} function",
                    Environment={
                        'Variables': {
                            'ENVIRONMENT': self.environment
                        }
                    }
                )

                deployed_functions[function_type] = response['FunctionArn']
                logger.info(f"Created Lambda function: {function_name}")

            except Exception as e:
                logger.error(f"Failed to create Lambda function {function_name}: {str(e)}")
                # Continue with other functions - Lambda functions are not critical for initial migration

        return deployed_functions

    def migrate_data_from_sheets(self, table_names: Dict[str, str]) -> bool:
        """
        Migrate data from Google Sheets to DynamoDB.

        Args:
            table_names: Dictionary mapping table types to DynamoDB table names

        Returns:
            True if migration successful, False otherwise
        """
        try:
            # Import the sheets connector
            from core.oauth_sheets_connector import (
                get_plants_data, get_products_data, get_kits_data,
                get_users_data, get_plant_products_data, get_user_plants_data
            )

            # Import DynamoDB connector
            from aws.dynamo_connector import DynamoConnector

            # Configure the connector to use the correct table names with full naming convention
            dynamo = DynamoConnector(
                region_name=self.region,
                table_prefix=f"{self.project_name}-"  # Use dash prefix to match created tables
            )

            # Override the table name method to use the full table names
            original_get_table_name = dynamo._get_table_name

            def get_full_table_name(table_type: str) -> str:
                return table_names.get(table_type, f"{self.project_name}-{table_type}-{self.environment}")

            dynamo._get_table_name = get_full_table_name

            # Migrate plants data
            if 'plants' in table_names:
                logger.info("Migrating plants data...")
                plants_data = get_plants_data()
                for plant in plants_data:
                    dynamo.create_plant(plant)
                logger.info(f"Migrated {len(plants_data)} plants")

            # Migrate products data
            if 'products' in table_names:
                logger.info("Migrating products data...")
                products_data = get_products_data()
                for product in products_data:
                    dynamo.create_product(product)
                logger.info(f"Migrated {len(products_data)} products")

            # Migrate kits data
            if 'kits' in table_names:
                logger.info("Migrating kits data...")
                kits_data = get_kits_data()
                for kit in kits_data:
                    dynamo.create_kit(kit)
                logger.info(f"Migrated {len(kits_data)} kits")

            # Migrate users data
            if 'users' in table_names:
                logger.info("Migrating users data...")
                users_data = get_users_data()
                for user in users_data:
                    dynamo.create_user(user)
                logger.info(f"Migrated {len(users_data)} users")

            # Migrate plant-product relationships
            if 'plant_products' in table_names:
                logger.info("Migrating plant-product relationships...")
                try:
                    plant_products_data = get_plant_products_data()
                    # For relationship tables, we'll use direct table access
                    table = dynamo._get_table('plant_products')
                    for relationship in plant_products_data:
                        prepared_item = dynamo._prepare_item(relationship)
                        table.put_item(Item=prepared_item)
                    logger.info(f"Migrated {len(plant_products_data)} plant-product relationships")
                except Exception as e:
                    logger.warning(f"Could not migrate plant-product relationships: {e}")

            # Migrate user-plant relationships
            if 'user_plants' in table_names:
                logger.info("Migrating user-plant relationships...")
                try:
                    user_plants_data = get_user_plants_data()
                    # For relationship tables, we'll use direct table access
                    table = dynamo._get_table('user_plants')
                    for relationship in user_plants_data:
                        prepared_item = dynamo._prepare_item(relationship)
                        table.put_item(Item=prepared_item)
                    logger.info(f"Migrated {len(user_plants_data)} user-plant relationships")
                except Exception as e:
                    logger.warning(f"Could not migrate user-plant relationships: {e}")

            logger.info("Data migration completed successfully")
            return True

        except Exception as e:
            logger.error(f"Data migration failed: {str(e)}")
            return False

    def create_environment_file(self,
                                bucket_name: str,
                                table_names: Dict[str, str],
                                cognito_config: Dict[str, str],
                                lambda_functions: Dict[str, str]) -> None:
        """
        Create .env file with AWS configuration.

        Args:
            bucket_name: S3 bucket name
            table_names: DynamoDB table names
            cognito_config: Cognito configuration
            lambda_functions: Lambda function ARNs
        """
        env_content = f"""# GrowVRD AWS Configuration
ENVIRONMENT={self.environment}
AWS_REGION={self.region}

# S3 Configuration
S3_BUCKET={bucket_name}

# DynamoDB Tables
DYNAMODB_PLANTS_TABLE={table_names.get('plants', '')}
DYNAMODB_PRODUCTS_TABLE={table_names.get('products', '')}
DYNAMODB_KITS_TABLE={table_names.get('kits', '')}
DYNAMODB_USERS_TABLE={table_names.get('users', '')}
DYNAMODB_PLANT_PRODUCTS_TABLE={table_names.get('plant_products', '')}
DYNAMODB_USER_PLANTS_TABLE={table_names.get('user_plants', '')}
DYNAMODB_LOCAL_VENDORS_TABLE={table_names.get('local_vendors', '')}

# Cognito Configuration
COGNITO_USER_POOL_ID={cognito_config.get('user_pool_id', '')}
COGNITO_CLIENT_ID={cognito_config.get('client_id', '')}

# Lambda Functions
LAMBDA_RECOMMENDATION_ARN={lambda_functions.get('recommendation', '')}
LAMBDA_HEALTH_CHECK_ARN={lambda_functions.get('health_check', '')}
LAMBDA_USER_MANAGEMENT_ARN={lambda_functions.get('user_management', '')}

# Keep existing OpenAI and other configurations
# OPENAI_API_KEY=your-openai-key-here
# PERENUAL_API_KEY=your-perenual-key-here
"""

        try:
            with open('.env.aws', 'w') as f:
                f.write(env_content)

            logger.info("Created .env.aws file with AWS configuration")
            logger.info("Please update your .env file with the AWS configuration and add your API keys")

        except Exception as e:
            logger.error(f"Failed to create environment file: {str(e)}")

    def run_full_migration(self) -> bool:
        """
        Run the complete migration process.

        Returns:
            True if migration successful, False otherwise
        """
        try:
            logger.info("Starting GrowVRD AWS migration...")

            # Validate AWS credentials
            if not self.validate_aws_credentials():
                return False

            # Create S3 bucket
            bucket_name = self.create_s3_bucket()

            # Create DynamoDB tables
            table_names = self.create_dynamodb_tables()

            # Create Cognito User Pool
            cognito_config = self.create_cognito_user_pool()

            # Create Lambda execution role
            role_arn = self.create_lambda_execution_role()

            # Deploy Lambda functions
            lambda_functions = self.deploy_lambda_functions(role_arn)

            # Migrate data from Google Sheets
            data_migration_success = self.migrate_data_from_sheets(table_names)

            # Create environment configuration
            self.create_environment_file(bucket_name, table_names, cognito_config, lambda_functions)

            if data_migration_success:
                logger.info("🎉 GrowVRD AWS migration completed successfully!")
                logger.info("Next steps:")
                logger.info("1. Update your .env file with the AWS configuration from .env.aws")
                logger.info("2. Add your OpenAI and Perenual API keys to the .env file")
                logger.info("3. Test the AWS infrastructure with the health check endpoint")
                logger.info("4. Update your application to use AWS services instead of Google Sheets")
                return True
            else:
                logger.warning("Migration completed with data migration issues. Check logs for details.")
                return False

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            return False


def main():
    """Main function for running migration from command line."""
    import argparse

    parser = argparse.ArgumentParser(description='Migrate GrowVRD to AWS')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--environment', default='development', help='Environment name')

    args = parser.parse_args()

    # Set environment
    os.environ['ENVIRONMENT'] = args.environment

    # Run migration
    migrator = AWSMigrationManager(aws_region=args.region)
    success = migrator.run_full_migration()

    if success:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed. Check logs for details.")
        exit(1)


if __name__ == "__main__":
    main()