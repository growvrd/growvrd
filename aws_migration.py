"""
AWS Migration and Setup Script for GrowVRD

This script handles the complete migration from Google Sheets to AWS infrastructure,
including DynamoDB table creation, data migration, and service validation.
"""
import os
import json
import boto3
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from botocore.exceptions import ClientError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aws_migration')


class AWSMigrationManager:
    """
    Manages the complete AWS infrastructure setup and data migration
    """

    def __init__(self):
        """Initialize AWS migration manager"""
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.table_prefix = os.getenv('DYNAMODB_TABLE_PREFIX', 'growvrd')
        self.s3_bucket = os.getenv('S3_BUCKET_NAME', 'growvrd-storage')

        # Initialize AWS clients
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.s3 = boto3.client('s3', region_name=self.region)
        self.cognito = boto3.client('cognito-idp', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)

        logger.info(f"Initialized AWS migration manager for region: {self.region}")

    def create_dynamodb_tables(self) -> Dict[str, bool]:
        """
        Create all required DynamoDB tables with proper schemas

        Returns:
            Dictionary mapping table names to creation success status
        """
        tables_config = {
            'plants': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'name', 'AttributeType': 'S'},
                    {'AttributeName': 'scientific_name', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'name-index',
                        'KeySchema': [
                            {'AttributeName': 'name', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    },
                    {
                        'IndexName': 'scientific-name-index',
                        'KeySchema': [
                            {'AttributeName': 'scientific_name', 'KeyType': 'HASH'}
                        ],
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
                        'KeySchema': [
                            {'AttributeName': 'category', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            },
            'kits': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'difficulty', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'difficulty-index',
                        'KeySchema': [
                            {'AttributeName': 'difficulty', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            },
            'users': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'email', 'AttributeType': 'S'},
                    {'AttributeName': 'cognito_sub', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'email-index',
                        'KeySchema': [
                            {'AttributeName': 'email', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    },
                    {
                        'IndexName': 'cognito-sub-index',
                        'KeySchema': [
                            {'AttributeName': 'cognito_sub', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            },
            'plant_products': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'plant_id', 'AttributeType': 'S'},
                    {'AttributeName': 'product_id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'plant-index',
                        'KeySchema': [
                            {'AttributeName': 'plant_id', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    },
                    {
                        'IndexName': 'product-index',
                        'KeySchema': [
                            {'AttributeName': 'product_id', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            },
            'user_plants': {
                'AttributeDefinitions': [
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'user_id', 'AttributeType': 'S'},
                    {'AttributeName': 'plant_id', 'AttributeType': 'S'}
                ],
                'KeySchema': [
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'user-index',
                        'KeySchema': [
                            {'AttributeName': 'user_id', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    },
                    {
                        'IndexName': 'plant-index',
                        'KeySchema': [
                            {'AttributeName': 'plant_id', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'BillingMode': 'PAY_PER_REQUEST'
                    }
                ]
            }
        }

        results = {}

        for table_name, config in tables_config.items():
            full_table_name = f"{self.table_prefix}_{table_name}"

            try:
                # Check if table already exists
                try:
                    self.dynamodb.meta.client.describe_table(TableName=full_table_name)
                    logger.info(f"Table {full_table_name} already exists")
                    results[table_name] = True
                    continue
                except ClientError as e:
                    if e.response['Error']['Code'] != 'ResourceNotFoundException':
                        raise

                # Create table
                table_params = {
                    'TableName': full_table_name,
                    'BillingMode': 'PAY_PER_REQUEST',
                    **config
                }

                table = self.dynamodb.create_table(**table_params)

                # Wait for table to be created
                logger.info(f"Creating table {full_table_name}...")
                table.wait_until_exists()

                logger.info(f"Successfully created table: {full_table_name}")
                results[table_name] = True

            except Exception as e:
                logger.error(f"Failed to create table {full_table_name}: {str(e)}")
                results[table_name] = False

        return results

    def create_s3_bucket(self) -> bool:
        """
        Create S3 bucket for file storage

        Returns:
            True if bucket created or already exists
        """
        try:
            # Check if bucket already exists
            try:
                self.s3.head_bucket(Bucket=self.s3_bucket)
                logger.info(f"S3 bucket {self.s3_bucket} already exists")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    raise

            # Create bucket
            if self.region == 'us-east-1':
                # us-east-1 doesn't need LocationConstraint
                self.s3.create_bucket(Bucket=self.s3_bucket)
            else:
                self.s3.create_bucket(
                    Bucket=self.s3_bucket,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )

            # Configure bucket settings
            self.s3.put_bucket_encryption(
                Bucket=self.s3_bucket,
                ServerSideEncryptionConfiguration={
                    'Rules': [
                        {
                            'ApplyServerSideEncryptionByDefault': {
                                'SSEAlgorithm': 'AES256'
                            }
                        }
                    ]
                }
            )

            # Set bucket versioning
            self.s3.put_bucket_versioning(
                Bucket=self.s3_bucket,
                VersioningConfiguration={'Status': 'Enabled'}
            )

            # Configure CORS for web access
            self.s3.put_bucket_cors(
                Bucket=self.s3_bucket,
                CORSConfiguration={
                    'CORSRules': [
                        {
                            'AllowedHeaders': ['*'],
                            'AllowedMethods': ['GET', 'POST', 'PUT', 'DELETE'],
                            'AllowedOrigins': ['*'],
                            'ExposeHeaders': ['ETag'],
                            'MaxAgeSeconds': 3000
                        }
                    ]
                }
            )

            logger.info(f"Successfully created S3 bucket: {self.s3_bucket}")
            return True

        except Exception as e:
            logger.error(f"Failed to create S3 bucket: {str(e)}")
            return False

    def create_cognito_user_pool(self) -> Optional[str]:
        """
        Create Cognito User Pool for authentication

        Returns:
            User Pool ID if successful, None otherwise
        """
        try:
            user_pool_name = f"{self.table_prefix}-user-pool"

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
                AliasAttributes=['email'],
                UsernameConfiguration={
                    'CaseSensitive': False
                },
                Schema=[
                    {
                        'Name': 'email',
                        'AttributeDataType': 'String',
                        'Required': True,
                        'Mutable': True
                    },
                    {
                        'Name': 'given_name',
                        'AttributeDataType': 'String',
                        'Required': False,
                        'Mutable': True
                    },
                    {
                        'Name': 'family_name',
                        'AttributeDataType': 'String',
                        'Required': False,
                        'Mutable': True
                    }