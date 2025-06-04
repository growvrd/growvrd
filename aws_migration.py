"""
AWS Migration Utilities for GrowVRD

This module provides utilities for migrating GrowVRD from Replit to AWS infrastructure,
including DynamoDB setup, Lambda deployment, and environment configuration.
"""

import os
import json
import boto3
import logging
import zipfile
import shutil
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aws_migration')


class AWSMigrationManager:
    """Manages the migration process from Replit to AWS"""

    def __init__(self, aws_region: str = 'us-east-1'):
        """
        Initialize the migration manager.

        Args:
            aws_region: AWS region for deployment
        """
        self.region = aws_region
        self.session = boto3.Session(region_name=aws_region)

        # AWS service clients
        self.dynamodb = self.session.client('dynamodb')
        self.lambda_client = self.session.client('lambda')
        self.s3 = self.session.client('s3')
        self.cognito = self.session.client('cognito-idp')
        self.iam = self.session.client('iam')
        self.apigateway = self.session.client('apigateway')

        # Project configuration
        self.project_name = 'growvrd'
        self.environment = os.getenv('ENVIRONMENT', 'development')

    def validate_aws_credentials(self) -> bool:
        """
        Validate that AWS credentials are properly configured.

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            sts = self.session.client('sts')
            identity = sts.get_caller_identity()
            logger.info(f"AWS credentials validated for account: {identity['Account']}")
            return True
        except Exception as e:
            logger.error(f"AWS credentials validation failed: {str(e)}")
            return False

    def create_s3_bucket(self, bucket_name: Optional[str] = None) -> str:
        """
        Create S3 bucket for plant images and file storage.

        Args:
            bucket_name: Optional custom bucket name

        Returns:
            Bucket name that was created
        """
        if not bucket_name:
            bucket_name = f"{self.project_name}-storage-{self.environment}"

        try:
            # Check if bucket already exists
            try:
                self.s3.head_bucket(Bucket=bucket_name)
                logger.info(f"S3 bucket {bucket_name} already exists")
                return bucket_name
            except:
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
                            'AllowedMethods': ['GET', 'POST', 'PUT'],
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
        Create DynamoDB tables for GrowVRD data.

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
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
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
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            },
            'kits': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ]
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
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            },
            'plant_products': {
                'AttributeDefinitions': [
                    {'AttributeName': 'plant_id', 'AttributeType': 'S'},
                    {'AttributeName': 'product_id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'plant_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'product_id', 'KeyType': 'RANGE'}
                ]
            },
            'user_plants': {
                'AttributeDefinitions': [
                    {'AttributeName': 'user_id', 'AttributeType': 'S'},
                    {'AttributeName': 'plant_id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'plant_id', 'KeyType': 'RANGE'}
                ]
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
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
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
                table_config['BillingMode'] = 'PAY_PER_REQUEST'

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
            Dictionary with user pool ID and client ID
        """
        pool_name = f"{self.project_name}-users-{self.environment}"

        try:
            # Create user pool
            user_pool = self.cognito.create_user_pool(
                PoolName=pool_name,
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
                UsernameAttributes=['email'],
                Schema=[
                    {
                        'Name': 'email',
                        'AttributeDataType': 'String',
                        'Required': True,
                        'Mutable': True
                    },
                    {
                        'Name': 'name',
                        'AttributeDataType': 'String',
                        'Required': False,
                        'Mutable': True
                    }
                ]
            )

            user_pool_id = user_pool['UserPool']['Id']
            logger.info(f"Created Cognito User Pool: {user_pool_id}")

            # Create user pool client
            client = self.cognito.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName=f"{self.project_name}-client-{self.environment}",
                GenerateSecret=False,
                ExplicitAuthFlows=[
                    'ADMIN_NO_SRP_AUTH',
                    'USER_PASSWORD_AUTH'
                ]
            )

            client_id = client['UserPoolClient']['ClientId']
            logger.info(f"Created Cognito User Pool Client: {client_id}")

            return {
                'user_pool_id': user_pool_id,
                'client_id': client_id
            }

        except Exception as e:
            logger.error(f"Failed to create Cognito User Pool: {str(e)}")
            raise

    def create_lambda_execution_role(self) -> str:
        """
        Create IAM role for Lambda function execution.

        Returns:
            ARN of the created role
        """
        role_name = f"{self.project_name}-lambda-role-{self.environment}"

        try:
            # Check if role already exists
            try:
                role = self.iam.get_role(RoleName=role_name)
                logger.info(f"Lambda execution role {role_name} already exists")
                return role['Role']['Arn']
            except self.iam.exceptions.NoSuchEntityException:
                pass

            # Create trust policy
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

            # Create role
            role = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Execution role for {self.project_name} Lambda functions"
            )

            role_arn = role['Role']['Arn']

            # Attach basic execution policy
            self.iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
            )

            # Create and attach custom policy for GrowVRD resources
            custom_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:UpdateItem",
                            "dynamodb:DeleteItem",
                            "dynamodb:Query",
                            "dynamodb:Scan"
                        ],
                        "Resource": f"arn:aws:dynamodb:{self.region}:*:table/{self.project_name}-*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:DeleteObject"
                        ],
                        "Resource": f"arn:aws:s3:::{self.project_name}-*/*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "cognito-idp:AdminGetUser",
                            "cognito-idp:AdminCreateUser",
                            "cognito-idp:AdminUpdateUserAttributes"
                        ],
                        "Resource": f"arn:aws:cognito-idp:{self.region}:*:userpool/*"
                    }
                ]
            }

            policy_name = f"{self.project_name}-lambda-policy-{self.environment}"
            self.iam.create_policy(
                PolicyName=policy_name,
                PolicyDocument=json.dumps(custom_policy),
                Description=f"Custom policy for {self.project_name} Lambda functions"
            )

            # Get account ID for policy ARN
            account_id = self.session.client('sts').get_caller_identity()['Account']
            policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"

            self.iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )

            logger.info(f"Created Lambda execution role: {role_arn}")
            return role_arn

        except Exception as e:
            logger.error(f"Failed to create Lambda execution role: {str(e)}")
            raise

    def package_lambda_function(self, function_name: str) -> str:
        """
        Package a Lambda function for deployment.

        Args:
            function_name: Name of the function file (without .py extension)

        Returns:
            Path to the created zip file
        """
        lambda_dir = Path("aws/lambda_functions")
        zip_path = f"/tmp/{function_name}.zip"

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add the specific function file
                function_file = lambda_dir / f"{function_name}.py"
                if function_file.exists():
                    zipf.write(function_file, f"{function_name}.py")

                # Add shared dependencies
                init_file = lambda_dir / "__init__.py"
                if init_file.exists():
                    zipf.write(init_file, "__init__.py")

                # Add core modules
                core_dir = Path("core")
                if core_dir.exists():
                    for file in core_dir.glob("*.py"):
                        zipf.write(file, f"core/{file.name}")

            logger.info(f"Packaged Lambda function: {zip_path}")
            return zip_path

        except Exception as e:
            logger.error(f"Failed to package Lambda function {function_name}: {str(e)}")
            raise

    def deploy_lambda_functions(self, role_arn: str) -> Dict[str, str]:
        """
        Deploy Lambda functions to AWS.

        Args:
            role_arn: ARN of the Lambda execution role

        Returns:
            Dictionary mapping function names to ARNs
        """
        functions = ['recommendation', 'health_check', 'user_management']
        deployed_functions = {}

        for function_name in functions:
            try:
                # Package function
                zip_path = self.package_lambda_function(function_name)

                # Read zip file
                with open(zip_path, 'rb') as f:
                    zip_content = f.read()

                lambda_function_name = f"{self.project_name}-{function_name}-{self.environment}"

                try:
                    # Try to update existing function
                    response = self.lambda_client.update_function_code(
                        FunctionName=lambda_function_name,
                        ZipFile=zip_content
                    )
                    logger.info(f"Updated Lambda function: {lambda_function_name}")

                except self.lambda_client.exceptions.ResourceNotFoundException:
                    # Create new function
                    response = self.lambda_client.create_function(
                        FunctionName=lambda_function_name,
                        Runtime='python3.9',
                        Role=role_arn,
                        Handler=f"{function_name}.lambda_handler",
                        Code={'ZipFile': zip_content},
                        Description=f"GrowVRD {function_name} function",
                        Timeout=300,
                        MemorySize=512,
                        Environment={
                            'Variables': {
                                'ENVIRONMENT': self.environment,
                                'AWS_REGION': self.region,
                                'PROJECT_NAME': self.project_name
                            }
                        }
                    )
                    logger.info(f"Created Lambda function: {lambda_function_name}")

                deployed_functions[function_name] = response['FunctionArn']

                # Clean up zip file
                os.remove(zip_path)

            except Exception as e:
                logger.error(f"Failed to deploy Lambda function {function_name}: {str(e)}")
                raise

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

            dynamo = DynamoConnector(region=self.region)

            # Migrate plants data
            if 'plants' in table_names:
                logger.info("Migrating plants data...")
                plants_data = get_plants_data()
                for plant in plants_data:
                    dynamo.put_item(table_names['plants'], plant)
                logger.info(f"Migrated {len(plants_data)} plants")

            # Migrate products data
            if 'products' in table_names:
                logger.info("Migrating products data...")
                products_data = get_products_data()
                for product in products_data:
                    dynamo.put_item(table_names['products'], product)
                logger.info(f"Migrated {len(products_data)} products")

            # Migrate kits data
            if 'kits' in table_names:
                logger.info("Migrating kits data...")
                kits_data = get_kits_data()
                for kit in kits_data:
                    dynamo.put_item(table_names['kits'], kit)
                logger.info(f"Migrated {len(kits_data)} kits")

            # Migrate users data
            if 'users' in table_names:
                logger.info("Migrating users data...")
                users_data = get_users_data()
                for user in users_data:
                    dynamo.put_item(table_names['users'], user)
                logger.info(f"Migrated {len(users_data)} users")

            # Migrate plant-product relationships
            if 'plant_products' in table_names:
                logger.info("Migrating plant-product relationships...")
                plant_products_data = get_plant_products_data()
                for relationship in plant_products_data:
                    dynamo.put_item(table_names['plant_products'], relationship)
                logger.info(f"Migrated {len(plant_products_data)} plant-product relationships")

            # Migrate user-plant relationships
            if 'user_plants' in table_names:
                logger.info("Migrating user-plant relationships...")
                user_plants_data = get_user_plants_data()
                for relationship in user_plants_data:
                    dynamo.put_item(table_names['user_plants'], relationship)
                logger.info(f"Migrated {len(user_plants_data)} user-plant relationships")

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