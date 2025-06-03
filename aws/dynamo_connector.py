"""
AWS DynamoDB Connector for GrowVRD

This module provides a scalable database layer using DynamoDB to replace Google Sheets.
Handles plant data, user management, and all other data operations with proper caching.
"""
import os
import json
import logging
import uuid
import time
from decimal import Decimal
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
from functools import wraps

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError, BotoCoreError
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dynamo_connector')


class DynamoConnectionError(Exception):
    """Exception raised for DynamoDB connection errors"""
    pass


class DynamoDataError(Exception):
    """Exception raised for DynamoDB data errors"""
    pass


class DynamoConnector:
    """
    DynamoDB connector with connection pooling, caching, and error handling
    """

    def __init__(self, region_name: str = None, table_prefix: str = 'growvrd'):
        """
        Initialize DynamoDB connector

        Args:
            region_name: AWS region (defaults to environment variable)
            table_prefix: Prefix for table names
        """
        self.region_name = region_name or os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.table_prefix = table_prefix
        self._dynamodb = None
        self._tables = {}
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes default

        # Initialize connection
        self._connect()

    def _connect(self):
        """Initialize DynamoDB connection"""
        try:
            # Use environment variables for AWS credentials
            session = boto3.Session(
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=self.region_name
            )

            self._dynamodb = session.resource('dynamodb')
            logger.info(f"Connected to DynamoDB in region {self.region_name}")

        except Exception as e:
            error_msg = f"Failed to connect to DynamoDB: {str(e)}"
            logger.error(error_msg)
            raise DynamoConnectionError(error_msg)

    def _get_table_name(self, table_type: str) -> str:
        """Get full table name with prefix"""
        return f"{self.table_prefix}_{table_type}"

    def _get_table(self, table_type: str):
        """Get table reference with caching"""
        table_name = self._get_table_name(table_type)

        if table_name not in self._tables:
            try:
                table = self._dynamodb.Table(table_name)
                # Verify table exists by calling describe_table
                table.meta.client.describe_table(TableName=table_name)
                self._tables[table_name] = table
                logger.debug(f"Connected to table: {table_name}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    logger.error(f"Table {table_name} does not exist")
                    raise DynamoDataError(f"Table {table_name} not found")
                else:
                    logger.error(f"Error accessing table {table_name}: {str(e)}")
                    raise DynamoConnectionError(f"Cannot access table {table_name}")

        return self._tables[table_name]

    def _cache_key(self, table_type: str, key: str = None) -> str:
        """Generate cache key"""
        if key:
            return f"{table_type}:{key}"
        return f"{table_type}:all"

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get item from cache if not expired"""
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Cache hit: {cache_key}")
                return data
            else:
                # Remove expired item
                del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: Any):
        """Set item in cache"""
        self._cache[cache_key] = (data, time.time())
        logger.debug(f"Cache set: {cache_key}")

    def _clear_cache(self, pattern: str = None):
        """Clear cache items matching pattern"""
        if pattern:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()
        logger.debug(f"Cache cleared: {pattern or 'all'}")

    def _convert_decimals(self, obj):
        """Convert DynamoDB Decimal objects to float/int"""
        if isinstance(obj, list):
            return [self._convert_decimals(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: self._convert_decimals(value) for key, value in obj.items()}
        elif isinstance(obj, Decimal):
            # Convert to int if it's a whole number, otherwise float
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        else:
            return obj

    def _prepare_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare item for DynamoDB (convert floats to Decimal)"""

        def convert_floats(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, list):
                return [convert_floats(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: convert_floats(value) for key, value in obj.items()}
            else:
                return obj

        # Add timestamps
        now = datetime.now().isoformat()
        prepared = convert_floats(item.copy())

        if 'created_at' not in prepared:
            prepared['created_at'] = now
        prepared['updated_at'] = now

        return prepared

    # Plants operations
    def get_plants(self) -> List[Dict[str, Any]]:
        """Get all plants from DynamoDB"""
        cache_key = self._cache_key('plants')
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('plants')
            response = table.scan()

            plants = []
            for item in response.get('Items', []):
                plants.append(self._convert_decimals(item))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    plants.append(self._convert_decimals(item))

            self._set_cache(cache_key, plants)
            logger.info(f"Retrieved {len(plants)} plants from DynamoDB")
            return plants

        except Exception as e:
            logger.error(f"Error retrieving plants: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve plants: {str(e)}")

    def get_plant(self, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get specific plant by ID"""
        cache_key = self._cache_key('plants', plant_id)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('plants')
            response = table.get_item(Key={'id': plant_id})

            if 'Item' in response:
                plant = self._convert_decimals(response['Item'])
                self._set_cache(cache_key, plant)
                return plant

            return None

        except Exception as e:
            logger.error(f"Error retrieving plant {plant_id}: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve plant: {str(e)}")

    def create_plant(self, plant_data: Dict[str, Any]) -> bool:
        """Create new plant"""
        try:
            table = self._get_table('plants')

            # Ensure plant has an ID
            if 'id' not in plant_data:
                plant_data['id'] = f"p{uuid.uuid4().hex[:8]}"

            prepared_item = self._prepare_item(plant_data)
            table.put_item(Item=prepared_item)

            # Clear cache
            self._clear_cache('plants')

            logger.info(f"Created plant: {plant_data['id']}")
            return True

        except Exception as e:
            logger.error(f"Error creating plant: {str(e)}")
            raise DynamoDataError(f"Failed to create plant: {str(e)}")

    def update_plant(self, plant_id: str, updates: Dict[str, Any]) -> bool:
        """Update existing plant"""
        try:
            table = self._get_table('plants')

            # Build update expression
            update_expr = "SET "
            expr_attr_values = {}
            expr_attr_names = {}

            updates['updated_at'] = datetime.now().isoformat()

            for key, value in updates.items():
                # Handle reserved words
                attr_name = f"#{key}"
                attr_value = f":{key}"

                update_expr += f"{attr_name} = {attr_value}, "
                expr_attr_names[attr_name] = key
                expr_attr_values[attr_value] = self._prepare_item({key: value})[key]

            update_expr = update_expr.rstrip(', ')

            table.update_item(
                Key={'id': plant_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values
            )

            # Clear cache
            self._clear_cache('plants')

            logger.info(f"Updated plant: {plant_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating plant {plant_id}: {str(e)}")
            raise DynamoDataError(f"Failed to update plant: {str(e)}")

    # Users operations
    def get_users(self) -> List[Dict[str, Any]]:
        """Get all users from DynamoDB"""
        cache_key = self._cache_key('users')
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('users')
            response = table.scan()

            users = []
            for item in response.get('Items', []):
                users.append(self._convert_decimals(item))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    users.append(self._convert_decimals(item))

            self._set_cache(cache_key, users)
            logger.info(f"Retrieved {len(users)} users from DynamoDB")
            return users

        except Exception as e:
            logger.error(f"Error retrieving users: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve users: {str(e)}")

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email using GSI"""
        cache_key = self._cache_key('users', email)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('users')

            # Query the email GSI
            response = table.query(
                IndexName='email-index',
                KeyConditionExpression=Key('email').eq(email)
            )

            if response['Items']:
                user = self._convert_decimals(response['Items'][0])
                self._set_cache(cache_key, user)
                return user

            return None

        except Exception as e:
            logger.error(f"Error retrieving user by email {email}: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve user: {str(e)}")

    def create_user(self, user_data: Dict[str, Any]) -> bool:
        """Create new user"""
        try:
            table = self._get_table('users')

            # Ensure user has an ID
            if 'id' not in user_data:
                user_data['id'] = f"u{uuid.uuid4().hex[:8]}"

            # Set default subscription status
            if 'subscription_status' not in user_data:
                user_data['subscription_status'] = 'free'

            prepared_item = self._prepare_item(user_data)
            table.put_item(Item=prepared_item)

            # Clear cache
            self._clear_cache('users')

            logger.info(f"Created user: {user_data['email']}")
            return True

        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise DynamoDataError(f"Failed to create user: {str(e)}")

    # Products operations
    def get_products(self) -> List[Dict[str, Any]]:
        """Get all products from DynamoDB"""
        cache_key = self._cache_key('products')
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('products')
            response = table.scan()

            products = []
            for item in response.get('Items', []):
                products.append(self._convert_decimals(item))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    products.append(self._convert_decimals(item))

            self._set_cache(cache_key, products)
            logger.info(f"Retrieved {len(products)} products from DynamoDB")
            return products

        except Exception as e:
            logger.error(f"Error retrieving products: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve products: {str(e)}")

    def create_product(self, product_data: Dict[str, Any]) -> bool:
        """Create new product"""
        try:
            table = self._get_table('products')

            # Ensure product has an ID
            if 'id' not in product_data:
                product_data['id'] = f"pr{uuid.uuid4().hex[:8]}"

            prepared_item = self._prepare_item(product_data)
            table.put_item(Item=prepared_item)

            # Clear cache
            self._clear_cache('products')

            logger.info(f"Created product: {product_data['id']}")
            return True

        except Exception as e:
            logger.error(f"Error creating product: {str(e)}")
            raise DynamoDataError(f"Failed to create product: {str(e)}")

    # Kits operations
    def get_kits(self) -> List[Dict[str, Any]]:
        """Get all kits from DynamoDB"""
        cache_key = self._cache_key('kits')
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('kits')
            response = table.scan()

            kits = []
            for item in response.get('Items', []):
                kits.append(self._convert_decimals(item))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    kits.append(self._convert_decimals(item))

            self._set_cache(cache_key, kits)
            logger.info(f"Retrieved {len(kits)} kits from DynamoDB")
            return kits

        except Exception as e:
            logger.error(f"Error retrieving kits: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve kits: {str(e)}")

    def create_kit(self, kit_data: Dict[str, Any]) -> bool:
        """Create new kit"""
        try:
            table = self._get_table('kits')

            # Ensure kit has an ID
            if 'id' not in kit_data:
                kit_data['id'] = f"k{uuid.uuid4().hex[:8]}"

            prepared_item = self._prepare_item(kit_data)
            table.put_item(Item=prepared_item)

            # Clear cache
            self._clear_cache('kits')

            logger.info(f"Created kit: {kit_data['id']}")
            return True

        except Exception as e:
            logger.error(f"Error creating kit: {str(e)}")
            raise DynamoDataError(f"Failed to create kit: {str(e)}")

    # Plant-Product relationships
    def get_plant_products(self) -> List[Dict[str, Any]]:
        """Get all plant-product relationships"""
        cache_key = self._cache_key('plant_products')
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            table = self._get_table('plant_products')
            response = table.scan()

            relationships = []
            for item in response.get('Items', []):
                relationships.append(self._convert_decimals(item))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    relationships.append(self._convert_decimals(item))

            self._set_cache(cache_key, relationships)
            logger.info(f"Retrieved {len(relationships)} plant-product relationships from DynamoDB")
            return relationships

        except Exception as e:
            logger.error(f"Error retrieving plant-product relationships: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve plant-product relationships: {str(e)}")

    def get_products_for_plant(self, plant_id: str) -> List[Dict[str, Any]]:
        """Get products compatible with a specific plant"""
        try:
            table = self._get_table('plant_products')

            response = table.query(
                IndexName='plant-index',
                KeyConditionExpression=Key('plant_id').eq(plant_id)
            )

            relationships = []
            for item in response.get('Items', []):
                relationships.append(self._convert_decimals(item))

            return relationships

        except Exception as e:
            logger.error(f"Error retrieving products for plant {plant_id}: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve products for plant: {str(e)}")

    # User-Plant relationships
    def get_user_plants(self, user_id: str) -> List[Dict[str, Any]]:
        """Get plants owned by a specific user"""
        try:
            table = self._get_table('user_plants')

            response = table.query(
                IndexName='user-index',
                KeyConditionExpression=Key('user_id').eq(user_id)
            )

            user_plants = []
            for item in response.get('Items', []):
                user_plants.append(self._convert_decimals(item))

            return user_plants

        except Exception as e:
            logger.error(f"Error retrieving plants for user {user_id}: {str(e)}")
            raise DynamoDataError(f"Failed to retrieve user plants: {str(e)}")

    def add_user_plant(self, user_id: str, plant_id: str, plant_data: Dict[str, Any]) -> bool:
        """Add a plant to user's collection"""
        try:
            table = self._get_table('user_plants')

            # Create composite key
            item_id = f"{user_id}#{plant_id}#{uuid.uuid4().hex[:8]}"

            item = {
                'id': item_id,
                'user_id': user_id,
                'plant_id': plant_id,
                'acquisition_date': datetime.now().isoformat(),
                'health_status': 'healthy',
                **plant_data
            }

            prepared_item = self._prepare_item(item)
            table.put_item(Item=prepared_item)

            # Clear user-specific cache
            self._clear_cache(f'user_plants:{user_id}')

            logger.info(f"Added plant {plant_id} to user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding plant to user: {str(e)}")
            raise DynamoDataError(f"Failed to add plant to user: {str(e)}")

    # Batch operations
    def batch_create_plants(self, plants: List[Dict[str, Any]]) -> Dict[str, int]:
        """Batch create multiple plants"""
        try:
            table = self._get_table('plants')

            created_count = 0
            failed_count = 0

            # Process in batches of 25 (DynamoDB limit)
            batch_size = 25
            for i in range(0, len(plants), batch_size):
                batch = plants[i:i + batch_size]

                with table.batch_writer() as batch_writer:
                    for plant in batch:
                        try:
                            if 'id' not in plant:
                                plant['id'] = f"p{uuid.uuid4().hex[:8]}"

                            prepared_item = self._prepare_item(plant)
                            batch_writer.put_item(Item=prepared_item)
                            created_count += 1
                        except Exception as e:
                            logger.error(f"Error in batch create for plant {plant.get('id', 'unknown')}: {str(e)}")
                            failed_count += 1

            # Clear cache
            self._clear_cache('plants')

            logger.info(f"Batch created {created_count} plants, {failed_count} failed")
            return {'created': created_count, 'failed': failed_count}

        except Exception as e:
            logger.error(f"Error in batch create plants: {str(e)}")
            raise DynamoDataError(f"Failed to batch create plants: {str(e)}")

    # Health check and utilities
    def health_check(self) -> Dict[str, Any]:
        """Check DynamoDB connection and table status"""
        try:
            tables_status = {}
            table_types = ['plants', 'products', 'kits', 'users', 'plant_products', 'user_plants']

            for table_type in table_types:
                try:
                    table = self._get_table(table_type)
                    response = table.meta.client.describe_table(TableName=self._get_table_name(table_type))
                    tables_status[table_type] = {
                        'status': response['Table']['TableStatus'],
                        'item_count': response['Table']['ItemCount'],
                        'size_bytes': response['Table']['TableSizeBytes']
                    }
                except Exception as e:
                    tables_status[table_type] = {'status': 'ERROR', 'error': str(e)}

            return {
                'connection': 'healthy',
                'region': self.region_name,
                'tables': tables_status,
                'cache_size': len(self._cache),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                'connection': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# Global connector instance
_dynamo_connector = None


def get_dynamo_connector() -> DynamoConnector:
    """Get global DynamoDB connector instance"""
    global _dynamo_connector
    if _dynamo_connector is None:
        _dynamo_connector = DynamoConnector()
    return _dynamo_connector


# Convenience functions that match the Google Sheets interface
def get_plants_data() -> List[Dict[str, Any]]:
    """Get all plants (compatible with existing Google Sheets interface)"""
    return get_dynamo_connector().get_plants()


def get_products_data() -> List[Dict[str, Any]]:
    """Get all products (compatible with existing Google Sheets interface)"""
    return get_dynamo_connector().get_products()


def get_kits_data() -> List[Dict[str, Any]]:
    """Get all kits (compatible with existing Google Sheets interface)"""
    return get_dynamo_connector().get_kits()


def get_users_data() -> List[Dict[str, Any]]:
    """Get all users (compatible with existing Google Sheets interface)"""
    return get_dynamo_connector().get_users()


def get_plant_products_data() -> List[Dict[str, Any]]:
    """Get all plant-product relationships (compatible with existing Google Sheets interface)"""
    return get_dynamo_connector().get_plant_products()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email (compatible with existing Google Sheets interface)"""
    return get_dynamo_connector().get_user_by_email(email)


def get_user_subscription_status(email: str) -> str:
    """Get user subscription status (compatible with existing Google Sheets interface)"""
    user = get_user_by_email(email)
    if user and user.get('subscription_status'):
        return user['subscription_status'].lower()
    return 'free'


# Migration utilities
def migrate_from_google_sheets():
    """Migrate data from Google Sheets to DynamoDB"""
    try:
        # Import Google Sheets connector
        from core.oauth_sheets_connector import (
            get_plants_data as get_sheets_plants,
            get_products_data as get_sheets_products,
            get_kits_data as get_sheets_kits,
            get_users_data as get_sheets_users,
            get_plant_products_data as get_sheets_plant_products
        )

        connector = get_dynamo_connector()

        # Migrate plants
        logger.info("Migrating plants...")
        plants = get_sheets_plants()
        if plants:
            result = connector.batch_create_plants(plants)
            logger.info(f"Plants migration: {result}")

        # Migrate products
        logger.info("Migrating products...")
        products = get_sheets_products()
        for product in products:
            connector.create_product(product)

        # Migrate kits
        logger.info("Migrating kits...")
        kits = get_sheets_kits()
        for kit in kits:
            connector.create_kit(kit)

        # Migrate users
        logger.info("Migrating users...")
        users = get_sheets_users()
        for user in users:
            connector.create_user(user)

        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return False


if __name__ == "__main__":
    # Test the connector
    try:
        connector = get_dynamo_connector()
        health = connector.health_check()
        print("DynamoDB Health Check:", json.dumps(health, indent=2))
    except Exception as e:
        print(f"Error testing DynamoDB connector: {e}")