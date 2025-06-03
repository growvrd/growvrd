"""
AWS Lambda Function: Plant Recommendations

Serverless function for handling plant recommendation requests with optimized
performance and automatic scaling.
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional
import boto3
from decimal import Decimal

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main Lambda handler for plant recommendations

    Args:
        event: API Gateway event data
        context: Lambda context object

    Returns:
        API Gateway response
    """
    try:
        # Parse the incoming request
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event

        # Extract user preferences
        user_preferences = body.get('user_preferences', {})
        user_email = body.get('user_email')

        # Validate required parameters
        if not user_preferences.get('location'):
            return create_error_response(400, "Location is required")

        logger.info(f"Processing recommendation request for {user_email or 'anonymous'}")

        # Get recommendations
        recommendations = get_plant_recommendations(user_preferences, user_email)

        # Return successful response
        return create_success_response(recommendations)

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return create_error_response(400, "Invalid JSON in request body")

    except Exception as e:
        logger.error(f"Error processing recommendation request: {str(e)}")
        return create_error_response(500, "Internal server error")


def get_plant_recommendations(user_preferences: Dict[str, Any], user_email: str = None) -> Dict[str, Any]:
    """Get plant recommendations using DynamoDB data"""
    try:
        # Initialize DynamoDB connection
        dynamodb = boto3.resource('dynamodb')
        table_prefix = os.getenv('DYNAMODB_TABLE_PREFIX', 'growvrd')

        # Get data from DynamoDB tables
        plants_data = get_table_data(dynamodb, f'{table_prefix}_plants')
        products_data = get_table_data(dynamodb, f'{table_prefix}_products')
        kits_data = get_table_data(dynamodb, f'{table_prefix}_kits')
        plant_products_data = get_table_data(dynamodb, f'{table_prefix}_plant_products')

        # Get user subscription status if email provided
        subscription_tier = 'free'
        if user_email:
            user_data = get_user_by_email(dynamodb, f'{table_prefix}_users', user_email)
            if user_data:
                subscription_tier = user_data.get('subscription_status', 'free')

        # Apply filters and ranking
        filtered_plants = filter_plants(plants_data, user_preferences, subscription_tier)
        ranked_plants = rank_plants(filtered_plants, user_preferences)

        # Get compatible products and kits
        recommended_products = match_products_to_plants(ranked_plants, products_data, plant_products_data)
        recommended_kits = find_matching_kits(user_preferences.get('location'), kits_data, user_preferences)

        # Generate care schedule
        care_schedule = create_care_schedule(ranked_plants[:5])

        return {
            'plants': ranked_plants[:10],
            'products': recommended_products[:5],
            'kits': recommended_kits[:3],
            'care_schedule': care_schedule,
            'subscription_tier': subscription_tier,
            'stats': {
                'total_plants_found': len(ranked_plants),
                'total_products_found': len(recommended_products),
                'total_kits_found': len(recommended_kits)
            }
        }

    except Exception as e:
        logger.error(f"Error in get_plant_recommendations: {str(e)}")
        raise


def get_table_data(dynamodb, table_name: str) -> List[Dict[str, Any]]:
    """Get all data from a DynamoDB table"""
    try:
        table = dynamodb.Table(table_name)
        response = table.scan()
        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        return [convert_decimals(item) for item in items]

    except Exception as e:
        logger.error(f"Error getting data from {table_name}: {str(e)}")
        return []


def get_user_by_email(dynamodb, table_name: str, email: str) -> Optional[Dict[str, Any]]:
    """Get user by email from DynamoDB"""
    try:
        table = dynamodb.Table(table_name)
        response = table.query(
            IndexName='email-index',
            KeyConditionExpression='email = :email',
            ExpressionAttributeValues={':email': email}
        )

        if response['Items']:
            return convert_decimals(response['Items'][0])
        return None

    except Exception as e:
        logger.error(f"Error getting user by email: {str(e)}")
        return None


def convert_decimals(obj):
    """Convert DynamoDB Decimal objects to Python types"""
    if isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj


def filter_plants(plants_data: List[Dict[str, Any]], user_preferences: Dict[str, Any],
                  subscription_tier: str = 'free') -> List[Dict[str, Any]]:
    """Filter plants based on user preferences and subscription"""
    filtered_plants = plants_data.copy()

    # Filter by subscription tier
    if subscription_tier == 'free':
        filtered_plants = [p for p in filtered_plants if not p.get('is_premium_content', False)]

    # Filter by location
    location = user_preferences.get('location')
    if location:
        location_filtered = []
        for plant in filtered_plants:
            compatible_locations = plant.get('compatible_locations', [])
            if isinstance(compatible_locations, str):
                compatible_locations = [loc.strip() for loc in compatible_locations.split(',')]
            compatible_locations = [loc.lower() for loc in compatible_locations if loc]

            if location.lower() in compatible_locations:
                location_filtered.append(plant)
        filtered_plants = location_filtered

    # Filter by experience level
    experience_level = user_preferences.get('experience_level')
    if experience_level:
        difficulty_thresholds = {'beginner': 3, 'intermediate': 6, 'advanced': 10}
        max_difficulty = difficulty_thresholds.get(experience_level.lower(), 3)
        filtered_plants = [p for p in filtered_plants if p.get('difficulty', 10) <= max_difficulty]

    # Filter by maintenance preference
    maintenance = user_preferences.get('maintenance')
    if maintenance:
        maintenance_levels = {
            'low': ['low'],
            'medium': ['low', 'medium', 'moderate'],
            'high': ['low', 'medium', 'moderate', 'high']
        }
        allowed_levels = maintenance_levels.get(maintenance.lower(), ['low'])
        filtered_plants = [p for p in filtered_plants
                           if any(level in str(p.get('maintenance', '')).lower()
                                  for level in allowed_levels)]

    return filtered_plants


def rank_plants(plants: List[Dict[str, Any]], user_preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rank plants based on compatibility with user preferences"""
    if not plants:
        return []

    weights = {'location': 3.0, 'light': 2.5, 'maintenance': 2.0, 'experience_level': 1.5}

    for plant in plants:
        score = 0.0
        max_possible_score = 0.0

        # Location match (already filtered, so give full points)
        score += weights['location']
        max_possible_score += weights['location']

        # Light preference match
        if 'light' in user_preferences:
            light_weight = weights['light']
            max_possible_score += light_weight
            light_req = str(plant.get('led_light_requirements', '')).lower()
            if user_preferences['light'].lower() in light_req:
                score += light_weight

        # Experience level match
        if 'experience_level' in user_preferences:
            exp_weight = weights['experience_level']
            max_possible_score += exp_weight
            difficulty = plant.get('difficulty', 5)
            exp_level = user_preferences['experience_level'].lower()

            if ((exp_level == 'beginner' and difficulty <= 3) or
                    (exp_level == 'intermediate' and difficulty <= 6) or
                    (exp_level == 'advanced')):
                score += exp_weight

        # Calculate normalized score
        normalized_score = (score / max_possible_score * 100) if max_possible_score > 0 else 0
        plant['match_score'] = score
        plant['normalized_score'] = round(normalized_score, 1)

    return sorted(plants, key=lambda p: p.get('match_score', 0), reverse=True)


def match_products_to_plants(plants: List[Dict[str, Any]], products_data: List[Dict[str, Any]],
                             plant_product_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Match compatible products to selected plants"""
    if not plants or not products_data:
        return []

    needed_categories = set(['pot', 'soil'])

    # Determine needed categories based on plants
    for plant in plants[:5]:
        led_light_reqs = str(plant.get('led_light_requirements', '')).lower()
        if 'low' in led_light_reqs:
            needed_categories.add('grow_light')

        water_freq = plant.get('water_frequency_days', 0)
        if isinstance(water_freq, (int, float)) and water_freq <= 3:
            needed_categories.add('watering_system')

        humidity = str(plant.get('humidity_preference', '')).lower()
        if 'high' in humidity:
            needed_categories.add('humidifier')

    # Score products
    scored_products = []
    for product in products_data:
        category = str(product.get('category', '')).lower()
        score = 10 if category in needed_categories else 0

        if score > 0:
            product_copy = product.copy()
            product_copy['relevance_score'] = score
            scored_products.append(product_copy)

    return sorted(scored_products, key=lambda p: p.get('relevance_score', 0), reverse=True)


def find_matching_kits(location: str, kits_data: List[Dict[str, Any]],
                       user_preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find kits that match user criteria"""
    if not location or not kits_data:
        return []

    matching_kits = []
    for kit in kits_data:
        kit_locations = kit.get('locations', [])
        if isinstance(kit_locations, str):
            kit_locations = [loc.strip() for loc in kit_locations.split(',')]
        kit_locations = [loc.lower() for loc in kit_locations if loc]

        if location.lower() in kit_locations:
            kit_copy = kit.copy()
            kit_copy['relevance_score'] = 10
            matching_kits.append(kit_copy)

    return sorted(matching_kits, key=lambda k: k.get('relevance_score', 0), reverse=True)


def create_care_schedule(plants: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Create a care schedule for selected plants"""
    if not plants:
        return {'daily': [], 'weekly': [], 'monthly': [], 'quarterly': []}

    schedule = {'daily': [], 'weekly': [], 'monthly': [], 'quarterly': []}

    for plant in plants:
        plant_name = plant.get('name', 'Unknown plant').replace('_', ' ').title()

        # Water frequency
        water_frequency = plant.get('water_frequency_days', 7)
        if isinstance(water_frequency, (int, float)):
            water_task = {
                'plant': plant_name,
                'task': 'Water plant',
                'details': f'Water approximately every {water_frequency} days'
            }

            if water_frequency <= 1:
                schedule['daily'].append(water_task)
            elif water_frequency <= 7:
                schedule['weekly'].append(water_task)
            else:
                schedule['monthly'].append(water_task)

        # General care tasks
        schedule['weekly'].append({
            'plant': plant_name,
            'task': 'Inspect for pests',
            'details': 'Check leaves and stems for signs of pests or disease'
        })

    return schedule


def create_success_response(data: Any) -> Dict[str, Any]:
    """Create a successful API Gateway response"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({'success': True, 'data': data}, default=str)
    }


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create an error API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({'success': False, 'error': message})
    }