"""
User Management Lambda Function for GrowVRD

This Lambda function handles all user account operations including:
- User registration and authentication
- Profile management and updates
- Subscription status tracking
- Plant ownership and care history
- Custom configurations and preferences
"""

import json
import boto3
import logging
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp')
s3 = boto3.client('s3')

# Configuration from environment variables
import os

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
PROJECT_NAME = os.getenv('PROJECT_NAME', 'growvrd')

# AWS resource names
USERS_TABLE_NAME = os.getenv('DYNAMODB_USERS_TABLE', f'{PROJECT_NAME}-users-{ENVIRONMENT}')
USER_PLANTS_TABLE_NAME = os.getenv('DYNAMODB_USER_PLANTS_TABLE', f'{PROJECT_NAME}-user-plants-{ENVIRONMENT}')
COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
COGNITO_CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')
S3_BUCKET = os.getenv('S3_BUCKET', f'{PROJECT_NAME}-storage-{ENVIRONMENT}')

# Initialize DynamoDB tables
try:
    users_table = dynamodb.Table(USERS_TABLE_NAME)
    user_plants_table = dynamodb.Table(USER_PLANTS_TABLE_NAME)
except Exception as e:
    logger.error(f"Failed to initialize DynamoDB tables: {str(e)}")
    users_table = None
    user_plants_table = None


def lambda_handler(event, context):
    """
    Main Lambda handler for user management operations.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        JSON response with operation results
    """
    try:
        # Parse the request
        action = event.get('action')
        data = event.get('data', {})

        logger.info(f"Processing user management action: {action}")

        # Route to appropriate handler
        if action == 'create_user':
            return create_user(data)
        elif action == 'authenticate_user':
            return authenticate_user(data)
        elif action == 'get_user_profile':
            return get_user_profile(data)
        elif action == 'update_user_profile':
            return update_user_profile(data)
        elif action == 'delete_user':
            return delete_user(data)
        elif action == 'add_user_plant':
            return add_user_plant(data)
        elif action == 'update_plant_status':
            return update_plant_status(data)
        elif action == 'get_user_plants':
            return get_user_plants(data)
        elif action == 'remove_user_plant':
            return remove_user_plant(data)
        elif action == 'update_subscription':
            return update_subscription(data)
        elif action == 'save_custom_kit':
            return save_custom_kit(data)
        elif action == 'get_user_analytics':
            return get_user_analytics(data)
        elif action == 'update_preferences':
            return update_preferences(data)
        elif action == 'health_check':
            return health_check()
        else:
            return error_response(f"Unknown action: {action}", 400)

    except Exception as e:
        logger.error(f"User management error: {str(e)}", exc_info=True)
        return error_response(f"Internal server error: {str(e)}", 500)


def create_user(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new user account in both Cognito and DynamoDB.

    Args:
        data: User registration data

    Returns:
        Response with user creation status
    """
    try:
        email = data.get('email')
        password = data.get('password')
        name = data.get('name', '')
        preferences = data.get('preferences', {})

        if not email or not password:
            return error_response("Email and password are required", 400)

        # Create user in Cognito
        try:
            cognito_response = cognito.admin_create_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'name', 'Value': name},
                    {'Name': 'email_verified', 'Value': 'true'}
                ],
                TemporaryPassword=password,
                MessageAction='SUPPRESS'  # Don't send welcome email
            )

            cognito_user_id = cognito_response['User']['Username']

            # Set permanent password
            cognito.admin_set_user_password(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=email,
                Password=password,
                Permanent=True
            )

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'UsernameExistsException':
                return error_response("User with this email already exists", 409)
            else:
                logger.error(f"Cognito user creation failed: {str(e)}")
                return error_response(f"Failed to create user account: {error_code}", 500)

        # Create user record in DynamoDB
        user_id = str(uuid.uuid4())
        user_record = {
            'id': user_id,
            'cognito_user_id': cognito_user_id,
            'email': email,
            'name': name,
            'subscription_status': 'free',
            'join_date': datetime.utcnow().isoformat(),
            'last_login': datetime.utcnow().isoformat(),
            'preferences': preferences,
            'plants_owned': [],
            'kits_owned': [],
            'custom_configurations': {},
            'care_history': {},
            'notification_preferences': {
                'watering_reminders': True,
                'care_tips': True,
                'weekly_summary': True,
                'email_notifications': True
            },
            'room_conditions': {},
            'usage_statistics': {
                'recommendations_requested': 0,
                'plants_added': 0,
                'last_activity': datetime.utcnow().isoformat()
            },
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        users_table.put_item(Item=user_record)

        logger.info(f"Successfully created user: {email}")

        return success_response({
            'user_id': user_id,
            'email': email,
            'cognito_user_id': cognito_user_id,
            'subscription_status': 'free'
        }, "User created successfully")

    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return error_response(f"Failed to create user: {str(e)}", 500)


def authenticate_user(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Authenticate user and return user profile.

    Args:
        data: Authentication data (email, password)

    Returns:
        Response with authentication status and user data
    """
    try:
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return error_response("Email and password are required", 400)

        # Authenticate with Cognito
        try:
            auth_response = cognito.admin_initiate_auth(
                UserPoolId=COGNITO_USER_POOL_ID,
                ClientId=COGNITO_CLIENT_ID,
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password
                }
            )

            access_token = auth_response['AuthenticationResult']['AccessToken']

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['NotAuthorizedException', 'UserNotFoundException']:
                return error_response("Invalid email or password", 401)
            else:
                logger.error(f"Cognito authentication failed: {str(e)}")
                return error_response("Authentication failed", 500)

        # Get user profile from DynamoDB
        try:
            response = users_table.scan(
                FilterExpression='email = :email',
                ExpressionAttributeValues={':email': email}
            )

            if not response['Items']:
                return error_response("User profile not found", 404)

            user_profile = response['Items'][0]

            # Update last login
            users_table.update_item(
                Key={'id': user_profile['id']},
                UpdateExpression='SET last_login = :timestamp, updated_at = :timestamp',
                ExpressionAttributeValues={
                    ':timestamp': datetime.utcnow().isoformat()
                }
            )

            # Remove sensitive information
            safe_profile = {k: v for k, v in user_profile.items()
                            if k not in ['cognito_user_id']}

            logger.info(f"User authenticated successfully: {email}")

            return success_response({
                'access_token': access_token,
                'user_profile': safe_profile
            }, "Authentication successful")

        except Exception as e:
            logger.error(f"Error retrieving user profile: {str(e)}")
            return error_response("Failed to retrieve user profile", 500)

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return error_response(f"Authentication failed: {str(e)}", 500)


def get_user_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get user profile by user ID or email.

    Args:
        data: Request data with user_id or email

    Returns:
        Response with user profile data
    """
    try:
        user_id = data.get('user_id')
        email = data.get('email')

        if not user_id and not email:
            return error_response("User ID or email is required", 400)

        if user_id:
            # Get by user ID
            response = users_table.get_item(Key={'id': user_id})
            if 'Item' not in response:
                return error_response("User not found", 404)
            user_profile = response['Item']
        else:
            # Get by email
            response = users_table.scan(
                FilterExpression='email = :email',
                ExpressionAttributeValues={':email': email}
            )
            if not response['Items']:
                return error_response("User not found", 404)
            user_profile = response['Items'][0]

        # Remove sensitive information
        safe_profile = {k: v for k, v in user_profile.items()
                        if k not in ['cognito_user_id']}

        return success_response(safe_profile, "User profile retrieved successfully")

    except Exception as e:
        logger.error(f"Error retrieving user profile: {str(e)}")
        return error_response(f"Failed to retrieve user profile: {str(e)}", 500)


def update_user_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update user profile information.

    Args:
        data: Updated profile data

    Returns:
        Response with update status
    """
    try:
        user_id = data.get('user_id')
        updates = data.get('updates', {})

        if not user_id:
            return error_response("User ID is required", 400)

        if not updates:
            return error_response("No updates provided", 400)

        # Build update expression
        update_expression = "SET updated_at = :timestamp"
        expression_values = {':timestamp': datetime.utcnow().isoformat()}

        # Add allowed fields to update
        allowed_fields = [
            'name', 'preferences', 'notification_preferences',
            'room_conditions', 'subscription_status'
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                update_expression += f", {field} = :{field}"
                expression_values[f":{field}"] = value

        # Perform update
        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

        logger.info(f"User profile updated: {user_id}")

        return success_response({
            'user_id': user_id,
            'updated_fields': list(updates.keys())
        }, "Profile updated successfully")

    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        return error_response(f"Failed to update profile: {str(e)}", 500)


def delete_user(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete user account from both Cognito and DynamoDB.

    Args:
        data: Request data with user_id

    Returns:
        Response with deletion status
    """
    try:
        user_id = data.get('user_id')

        if not user_id:
            return error_response("User ID is required", 400)

        # Get user record to get Cognito user ID
        response = users_table.get_item(Key={'id': user_id})
        if 'Item' not in response:
            return error_response("User not found", 404)

        user_record = response['Item']
        cognito_user_id = user_record.get('cognito_user_id')
        email = user_record.get('email')

        # Delete from Cognito
        if cognito_user_id:
            try:
                cognito.admin_delete_user(
                    UserPoolId=COGNITO_USER_POOL_ID,
                    Username=cognito_user_id
                )
            except ClientError as e:
                logger.warning(f"Failed to delete Cognito user: {str(e)}")

        # Delete user plants
        try:
            plants_response = user_plants_table.scan(
                FilterExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id}
            )

            for plant in plants_response['Items']:
                user_plants_table.delete_item(
                    Key={
                        'user_id': plant['user_id'],
                        'plant_id': plant['plant_id']
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to delete user plants: {str(e)}")

        # Delete user record
        users_table.delete_item(Key={'id': user_id})

        logger.info(f"User deleted successfully: {email}")

        return success_response({
            'user_id': user_id,
            'email': email
        }, "User account deleted successfully")

    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return error_response(f"Failed to delete user: {str(e)}", 500)


def add_user_plant(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a plant to user's collection.

    Args:
        data: Plant ownership data

    Returns:
        Response with addition status
    """
    try:
        user_id = data.get('user_id')
        plant_id = data.get('plant_id')
        nickname = data.get('nickname', '')
        location_in_home = data.get('location_in_home', '')

        if not user_id or not plant_id:
            return error_response("User ID and plant ID are required", 400)

        # Create user-plant relationship
        user_plant_record = {
            'user_id': user_id,
            'plant_id': plant_id,
            'nickname': nickname,
            'acquisition_date': datetime.utcnow().isoformat(),
            'last_watered': None,
            'last_fertilized': None,
            'health_status': 'healthy',
            'location_in_home': location_in_home,
            'days_since_watered': 0,
            'care_notes': '',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        user_plants_table.put_item(Item=user_plant_record)

        # Update user's plants_owned list
        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression='SET plants_owned = list_append(if_not_exists(plants_owned, :empty_list), :plant_id), usage_statistics.plants_added = usage_statistics.plants_added + :one, updated_at = :timestamp',
            ExpressionAttributeValues={
                ':plant_id': [plant_id],
                ':empty_list': [],
                ':one': 1,
                ':timestamp': datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Plant added to user collection: {user_id} -> {plant_id}")

        return success_response({
            'user_id': user_id,
            'plant_id': plant_id,
            'nickname': nickname
        }, "Plant added to collection successfully")

    except Exception as e:
        logger.error(f"Error adding user plant: {str(e)}")
        return error_response(f"Failed to add plant: {str(e)}", 500)


def update_plant_status(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update the status of a user's plant.

    Args:
        data: Plant status update data

    Returns:
        Response with update status
    """
    try:
        user_id = data.get('user_id')
        plant_id = data.get('plant_id')
        updates = data.get('updates', {})

        if not user_id or not plant_id:
            return error_response("User ID and plant ID are required", 400)

        # Build update expression
        update_expression = "SET updated_at = :timestamp"
        expression_values = {':timestamp': datetime.utcnow().isoformat()}

        # Add allowed fields to update
        allowed_fields = [
            'nickname', 'last_watered', 'last_fertilized', 'health_status',
            'location_in_home', 'days_since_watered', 'care_notes'
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                update_expression += f", {field} = :{field}"
                expression_values[f":{field}"] = value

        # Update care history if watering or fertilizing
        if 'last_watered' in updates or 'last_fertilized' in updates:
            care_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'watered' if 'last_watered' in updates else 'fertilized',
                'notes': updates.get('care_notes', '')
            }

            # This would need a more complex update for care history
            # For now, we'll just update the basic fields

        # Perform update
        user_plants_table.update_item(
            Key={'user_id': user_id, 'plant_id': plant_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

        logger.info(f"Plant status updated: {user_id} -> {plant_id}")

        return success_response({
            'user_id': user_id,
            'plant_id': plant_id,
            'updated_fields': list(updates.keys())
        }, "Plant status updated successfully")

    except Exception as e:
        logger.error(f"Error updating plant status: {str(e)}")
        return error_response(f"Failed to update plant status: {str(e)}", 500)


def get_user_plants(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get all plants owned by a user.

    Args:
        data: Request data with user_id

    Returns:
        Response with user's plants
    """
    try:
        user_id = data.get('user_id')

        if not user_id:
            return error_response("User ID is required", 400)

        # Get user's plants
        response = user_plants_table.scan(
            FilterExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id}
        )

        plants = response['Items']

        return success_response({
            'user_id': user_id,
            'plants': plants,
            'total_plants': len(plants)
        }, "User plants retrieved successfully")

    except Exception as e:
        logger.error(f"Error retrieving user plants: {str(e)}")
        return error_response(f"Failed to retrieve plants: {str(e)}", 500)


def remove_user_plant(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove a plant from user's collection.

    Args:
        data: Plant removal data

    Returns:
        Response with removal status
    """
    try:
        user_id = data.get('user_id')
        plant_id = data.get('plant_id')

        if not user_id or not plant_id:
            return error_response("User ID and plant ID are required", 400)

        # Delete user-plant relationship
        user_plants_table.delete_item(
            Key={'user_id': user_id, 'plant_id': plant_id}
        )

        # Update user's plants_owned list (this is complex with DynamoDB)
        # For now, we'll just track the removal
        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression='SET updated_at = :timestamp',
            ExpressionAttributeValues={
                ':timestamp': datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Plant removed from user collection: {user_id} -> {plant_id}")

        return success_response({
            'user_id': user_id,
            'plant_id': plant_id
        }, "Plant removed from collection successfully")

    except Exception as e:
        logger.error(f"Error removing user plant: {str(e)}")
        return error_response(f"Failed to remove plant: {str(e)}", 500)


def update_subscription(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update user's subscription status.

    Args:
        data: Subscription update data

    Returns:
        Response with update status
    """
    try:
        user_id = data.get('user_id')
        subscription_status = data.get('subscription_status')
        subscription_metadata = data.get('subscription_metadata', {})

        if not user_id or not subscription_status:
            return error_response("User ID and subscription status are required", 400)

        valid_statuses = ['free', 'subscriber', 'premium']
        if subscription_status not in valid_statuses:
            return error_response(f"Invalid subscription status. Must be one of: {valid_statuses}", 400)

        # Update subscription
        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression='SET subscription_status = :status, subscription_metadata = :metadata, updated_at = :timestamp',
            ExpressionAttributeValues={
                ':status': subscription_status,
                ':metadata': subscription_metadata,
                ':timestamp': datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Subscription updated: {user_id} -> {subscription_status}")

        return success_response({
            'user_id': user_id,
            'subscription_status': subscription_status
        }, "Subscription updated successfully")

    except Exception as e:
        logger.error(f"Error updating subscription: {str(e)}")
        return error_response(f"Failed to update subscription: {str(e)}", 500)


def save_custom_kit(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save a custom plant kit configuration for a user.

    Args:
        data: Custom kit data

    Returns:
        Response with save status
    """
    try:
        user_id = data.get('user_id')
        kit_data = data.get('kit_data', {})

        if not user_id or not kit_data:
            return error_response("User ID and kit data are required", 400)

        # Generate kit ID if not provided
        kit_id = kit_data.get('kit_id', f"custom_{uuid.uuid4().hex[:8]}")

        # Add metadata
        kit_data.update({
            'kit_id': kit_id,
            'created_at': datetime.utcnow().isoformat(),
            'last_modified': datetime.utcnow().isoformat(),
            'is_custom': True
        })

        # Update user's custom configurations
        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression='SET custom_configurations.#kit_id = :kit_data, updated_at = :timestamp',
            ExpressionAttributeNames={'#kit_id': kit_id},
            ExpressionAttributeValues={
                ':kit_data': kit_data,
                ':timestamp': datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Custom kit saved: {user_id} -> {kit_id}")

        return success_response({
            'user_id': user_id,
            'kit_id': kit_id
        }, "Custom kit saved successfully")

    except Exception as e:
        logger.error(f"Error saving custom kit: {str(e)}")
        return error_response(f"Failed to save custom kit: {str(e)}", 500)


def get_user_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get analytics data for a user.

    Args:
        data: Request data with user_id

    Returns:
        Response with user analytics
    """
    try:
        user_id = data.get('user_id')

        if not user_id:
            return error_response("User ID is required", 400)

        # Get user record
        user_response = users_table.get_item(Key={'id': user_id})
        if 'Item' not in user_response:
            return error_response("User not found", 404)

        user_record = user_response['Item']

        # Get user plants for additional analytics
        plants_response = user_plants_table.scan(
            FilterExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id}
        )

        user_plants = plants_response['Items']

        # Calculate analytics
        analytics = {
            'user_id': user_id,
            'member_since': user_record.get('join_date'),
            'subscription_status': user_record.get('subscription_status', 'free'),
            'total_plants': len(user_plants),
            'plants_by_health': {},
            'plants_by_location': {},
            'care_activity': {
                'last_watered_plant': None,
                'last_fertilized_plant': None,
                'plants_needing_water': 0
            },
            'usage_statistics': user_record.get('usage_statistics', {}),
            'custom_kits_created': len(user_record.get('custom_configurations', {}))
        }

        # Analyze plant data
        for plant in user_plants:
            # Health status breakdown
            health_status = plant.get('health_status', 'unknown')
            analytics['plants_by_health'][health_status] = analytics['plants_by_health'].get(health_status, 0) + 1

            # Location breakdown
            location = plant.get('location_in_home', 'unknown')
            analytics['plants_by_location'][location] = analytics['plants_by_location'].get(location, 0) + 1

            # Care activity
            days_since_watered = plant.get('days_since_watered', 0)
            if days_since_watered > 7:  # Needs watering
                analytics['care_activity']['plants_needing_water'] += 1

        return success_response(analytics, "User analytics retrieved successfully")

    except Exception as e:
        logger.error(f"Error retrieving user analytics: {str(e)}")
        return error_response(f"Failed to retrieve analytics: {str(e)}", 500)


def update_preferences(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update user preferences and notification settings.

    Args:
        data: Preferences update data

    Returns:
        Response with update status
    """
    try:
        user_id = data.get('user_id')
        preferences = data.get('preferences', {})
        notification_preferences = data.get('notification_preferences', {})

        if not user_id:
            return error_response("User ID is required", 400)

        # Build update expression
        update_expression = "SET updated_at = :timestamp"
        expression_values = {':timestamp': datetime.utcnow().isoformat()}

        if preferences:
            update_expression += ", preferences = :preferences"
            expression_values[':preferences'] = preferences

        if notification_preferences:
            update_expression += ", notification_preferences = :notifications"
            expression_values[':notifications'] = notification_preferences

        # Perform update
        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

        logger.info(f"User preferences updated: {user_id}")

        return success_response({
            'user_id': user_id,
            'updated': True
        }, "Preferences updated successfully")

    except Exception as e:
        logger.error(f"Error updating preferences: {str(e)}")
        return error_response(f"Failed to update preferences: {str(e)}", 500)


def health_check() -> Dict[str, Any]:
    """
    Perform health check of user management system.

    Returns:
        Response with health status
    """
    try:
        health_status = {
            'service': 'user_management',
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {}
        }

        # Test DynamoDB connection
        try:
            users_table.scan(Limit=1)
            health_status['checks']['dynamodb_users'] = {'status': 'healthy', 'message': 'Table accessible'}
        except Exception as e:
            health_status['checks']['dynamodb_users'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['status'] = 'degraded'

        try:
            user_plants_table.scan(Limit=1)
            health_status['checks']['dynamodb_user_plants'] = {'status': 'healthy', 'message': 'Table accessible'}
        except Exception as e:
            health_status['checks']['dynamodb_user_plants'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['status'] = 'degraded'

        # Test Cognito connection
        try:
            if COGNITO_USER_POOL_ID:
                cognito.describe_user_pool(UserPoolId=COGNITO_USER_POOL_ID)
                health_status['checks']['cognito'] = {'status': 'healthy', 'message': 'User pool accessible'}
            else:
                health_status['checks']['cognito'] = {'status': 'not_configured', 'message': 'User pool ID not set'}
        except Exception as e:
            health_status['checks']['cognito'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['status'] = 'degraded'

        # Check configuration
        config_issues = []
        if not COGNITO_USER_POOL_ID:
            config_issues.append('COGNITO_USER_POOL_ID not configured')
        if not COGNITO_CLIENT_ID:
            config_issues.append('COGNITO_CLIENT_ID not configured')

        health_status['configuration'] = {
            'issues': config_issues,
            'environment': ENVIRONMENT,
            'region': AWS_REGION
        }

        if config_issues:
            health_status['status'] = 'degraded'

        return success_response(health_status, "Health check completed")

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return error_response(f"Health check failed: {str(e)}", 500)


def success_response(data: Dict[str, Any], message: str = "Success") -> Dict[str, Any]:
    """
    Create a standardized success response.

    Args:
        data: Response data
        message: Success message

    Returns:
        Formatted success response
    """
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'success': True,
            'message': message,
            'data': data,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }, default=str)
    }


def error_response(message: str, status_code: int = 500) -> Dict[str, Any]:
    """
    Create a standardized error response.

    Args:
        message: Error message
        status_code: HTTP status code

    Returns:
        Formatted error response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'success': False,
            'error': True,
            'message': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: Email address to validate

    Returns:
        True if valid, False otherwise
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}
    return re.match(pattern, email) is not None


def hash_password(password: str) -> str:
    """
    Hash a password for storage (not used with Cognito, but useful for other purposes).

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return hashlib.sha256(password.encode()).hexdigest()


def generate_user_id() -> str:
    """
    Generate a unique user ID.

    Returns:
        Unique user ID
    """
    return str(uuid.uuid4())


def calculate_days_since_watered(last_watered: Optional[str]) -> int:
    """
    Calculate days since a plant was last watered.

    Args:
        last_watered: ISO timestamp of last watering

    Returns:
        Number of days since last watering
    """
    if not last_watered:
        return 0

    try:
        last_watered_date = datetime.fromisoformat(last_watered.replace('Z', '+00:00'))
        now = datetime.utcnow().replace(tzinfo=last_watered_date.tzinfo)
        delta = now - last_watered_date
        return delta.days
    except Exception:
        return 0


def get_user_statistics(user_id: str) -> Dict[str, Any]:
    """
    Get comprehensive statistics for a user.

    Args:
        user_id: User ID

    Returns:
        Dictionary with user statistics
    """
    try:
        # Get user record
        user_response = users_table.get_item(Key={'id': user_id})
        if 'Item' not in user_response:
            return {}

        user_record = user_response['Item']

        # Get user plants
        plants_response = user_plants_table.scan(
            FilterExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id}
        )

        user_plants = plants_response['Items']

        # Calculate statistics
        stats = {
            'total_plants': len(user_plants),
            'healthy_plants': len([p for p in user_plants if p.get('health_status') == 'healthy']),
            'plants_needing_attention': len(
                [p for p in user_plants if p.get('health_status') in ['needs_attention', 'declining']]),
            'average_days_since_watered': 0,
            'most_recent_plant_added': None,
            'member_since_days': 0
        }

        # Calculate average days since watered
        if user_plants:
            total_days = sum(p.get('days_since_watered', 0) for p in user_plants)
            stats['average_days_since_watered'] = total_days / len(user_plants)

            # Find most recent plant
            recent_plant = max(user_plants, key=lambda p: p.get('acquisition_date', ''))
            stats['most_recent_plant_added'] = recent_plant.get('acquisition_date')

        # Calculate member since days
        join_date = user_record.get('join_date')
        if join_date:
            try:
                join_datetime = datetime.fromisoformat(join_date.replace('Z', '+00:00'))
                now = datetime.utcnow().replace(tzinfo=join_datetime.tzinfo)
                stats['member_since_days'] = (now - join_datetime).days
            except Exception:
                pass

        return stats

    except Exception as e:
        logger.error(f"Error calculating user statistics: {str(e)}")
        return {}


# Batch operations for efficiency
def batch_update_plant_care(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update care information for multiple plants at once.

    Args:
        data: Batch update data

    Returns:
        Response with batch update status
    """
    try:
        user_id = data.get('user_id')
        plant_updates = data.get('plant_updates', [])

        if not user_id or not plant_updates:
            return error_response("User ID and plant updates are required", 400)

        updated_plants = []
        failed_updates = []

        for update in plant_updates:
            plant_id = update.get('plant_id')
            care_data = update.get('care_data', {})

            try:
                # Update individual plant
                result = update_plant_status({
                    'user_id': user_id,
                    'plant_id': plant_id,
                    'updates': care_data
                })

                if result['statusCode'] == 200:
                    updated_plants.append(plant_id)
                else:
                    failed_updates.append({'plant_id': plant_id, 'error': 'Update failed'})

            except Exception as e:
                failed_updates.append({'plant_id': plant_id, 'error': str(e)})

        return success_response({
            'user_id': user_id,
            'updated_plants': updated_plants,
            'failed_updates': failed_updates,
            'total_attempted': len(plant_updates)
        }, f"Batch update completed: {len(updated_plants)} success, {len(failed_updates)} failed")

    except Exception as e:
        logger.error(f"Error in batch plant update: {str(e)}")
        return error_response(f"Batch update failed: {str(e)}", 500)


# Usage tracking functions
def track_user_activity(user_id: str, activity_type: str, metadata: Dict[str, Any] = None) -> None:
    """
    Track user activity for analytics.

    Args:
        user_id: User ID
        activity_type: Type of activity
        metadata: Additional activity metadata
    """
    try:
        # Update usage statistics
        update_expression = "SET usage_statistics.last_activity = :timestamp"
        expression_values = {':timestamp': datetime.utcnow().isoformat()}

        if activity_type == 'recommendation_requested':
            update_expression += ", usage_statistics.recommendations_requested = if_not_exists(usage_statistics.recommendations_requested, :zero) + :one"
            expression_values[':one'] = 1
            expression_values[':zero'] = 0

        users_table.update_item(
            Key={'id': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

    except Exception as e:
        logger.warning(f"Failed to track user activity: {str(e)}")


# For testing locally
if __name__ == "__main__":
    # Test event
    test_event = {
        'action': 'health_check'
    }


    # Mock context
    class MockContext:
        def __init__(self):
            self.function_name = 'growvrd-user-management-development'
            self.function_version = '1'
            self.memory_limit_in_mb = 384


    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2, default=str))