import logging
from typing import Dict, Any, List, Union, Optional
import json
import re
import os
from logging.handlers import RotatingFileHandler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('data_handler')

# Define supported type conversions
SUPPORTED_TYPES = ['string', 'number', 'integer', 'float', 'list', 'boolean', 'dict']

# Define subscription tier constants
SUBSCRIPTION_TIERS = {
    "FREE": "free",
    "SUBSCRIBER": "subscriber"
}


class DataValidationError(Exception):
    """Custom exception for data validation errors"""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        self.field = field
        self.value = value
        self.message = message
        super().__init__(f"{message} (Field: {field}, Value: {value})")


def setup_logging(log_level: str = "INFO") -> None:
    """
    Set up logging with proper configuration for production/development.

    Args:
        log_level (str): Desired logging level
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Set different handlers based on environment
    if os.environ.get("ENVIRONMENT") == "production":
        # In production, log to file with rotation
        handler = RotatingFileHandler(
            "growvrd.log", maxBytes=10485760, backupCount=5
        )
    else:
        # In development, log to console
        handler = logging.StreamHandler()

    handler.setFormatter(logging.Formatter(log_format))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def parse_sheet_data(raw_data: Dict[str, Any], expected_types: Dict[str, str]) -> Dict[str, Any]:
    """
    Parse data from Google Sheets with proper type conversion and validation.

    Args:
        raw_data (dict): Raw data from Google Sheets
        expected_types (dict): Expected data types for each field
            Supported types: 'string', 'number', 'integer', 'float', 'list', 'boolean', 'dict'

    Returns:
        dict: Properly formatted data with correct types

    Raises:
        DataValidationError: If critical data validation fails
    """
    if not raw_data:
        logger.warning("Empty raw data received")
        return {}

    if not expected_types:
        logger.warning("No expected types provided, returning raw data")
        return raw_data

    parsed_data = {}

    # Check for unsupported type definitions
    unsupported_types = [t for t in expected_types.values() if t not in SUPPORTED_TYPES]
    if unsupported_types:
        logger.warning(f"Unsupported type(s) found: {unsupported_types}")

    # Process each field
    for key, value in raw_data.items():
        try:
            if key not in expected_types:
                # Keep as is if no type specified
                parsed_data[key] = value
                continue

            expected_type = expected_types[key]

            # Handle empty values with appropriate defaults
            if value is None or value == '':
                parsed_data[key] = _get_default_for_type(expected_type)
                continue

            # Convert to appropriate type
            parsed_data[key] = _convert_to_type(value, expected_type)

        except Exception as e:
            logger.error(f"Error processing field '{key}': {str(e)}")
            # Use default value for the expected type
            parsed_data[key] = _get_default_for_type(expected_types.get(key, 'string'))

    return parsed_data


def _get_default_for_type(expected_type: str) -> Any:
    """
    Returns the default value for a given type.

    Args:
        expected_type (str): The expected data type

    Returns:
        The appropriate default value for the type
    """
    if expected_type == 'list':
        return []
    elif expected_type in ('number', 'integer', 'float'):
        return 0
    elif expected_type == 'boolean':
        return False
    elif expected_type == 'dict':
        return {}
    else:  # string or unrecognized type
        return ''


def _convert_to_type(value: Any, expected_type: str) -> Any:
    """
    Converts a value to the expected type.

    Args:
        value: The value to convert
        expected_type (str): The expected data type

    Returns:
        The converted value

    Raises:
        ValueError: If the conversion fails
    """
    if expected_type == 'string':
        return str(value).strip()

    elif expected_type == 'number':
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert '{value}' to number")
            return 0

    elif expected_type == 'integer':
        try:
            return int(float(value))
        except (ValueError, TypeError):
            logger.warning(f"Could not convert '{value}' to integer")
            return 0

    elif expected_type == 'float':
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert '{value}' to float")
            return 0.0

    elif expected_type == 'list':
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            # Split by comma and strip whitespace
            return [item.strip() for item in value.split(',') if item.strip()]
        else:
            return [str(value)]

    elif expected_type == 'boolean':
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 't', 'y')
        elif isinstance(value, (int, float)):
            return value != 0
        else:
            return bool(value)

    elif expected_type == 'dict':
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse '{value}' as JSON dictionary")
                return {}
        else:
            logger.warning(f"Could not convert '{value}' to dictionary")
            return {}

    else:
        # If type is not recognized, return as string
        logger.warning(f"Unrecognized type '{expected_type}', treating as string")
        return str(value)


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
    """
    Validates that all required fields are present and have non-empty values.

    Args:
        data (dict): The data to validate
        required_fields (list): List of required field names

    Returns:
        list: List of missing or empty required fields
    """
    missing_fields = []

    for field in required_fields:
        if field not in data or data[field] == '' or data[field] is None:
            missing_fields.append(field)
        elif isinstance(data[field], list) and len(data[field]) == 0:
            missing_fields.append(field)
        elif isinstance(data[field], dict) and len(data[field]) == 0:
            missing_fields.append(field)

    return missing_fields


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email (str): Email to validate

    Returns:
        bool: True if valid, False otherwise
    """
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(re.match(email_pattern, email))


def calculate_kit_price(base_price: float, subscription_tier: str) -> float:
    """
    Calculate the final kit price based on subscription tier.

    Args:
        base_price (float): The base price of the kit
        subscription_tier (str): User's subscription tier

    Returns:
        float: The calculated price with appropriate markup
    """
    if subscription_tier == SUBSCRIPTION_TIERS["SUBSCRIBER"]:
        return round(base_price * 1.03, 2)  # 3% markup for subscribers
    else:
        return round(base_price * 1.10, 2)  # 10% markup for free users


# Schema definitions for different data types
def get_expected_plant_types() -> Dict[str, str]:
    """Get expected data types for plant fields"""
    return {
        "id": "string",
        "name": "string",
        "scientific_name": "string",
        "natural_sunlight_needs": "string",
        "natural_sunlight_required": "boolean",
        "led_light_requirements": "string",
        "recommended_light_wattage": "integer",
        "led_wattage_min": "integer",
        "led_wattage_max": "integer",
        "water_frequency_days": "integer",
        "humidity_preference": "string",
        "difficulty": "integer",
        "maintenance": "string",
        "indoor_compatible": "boolean",
        "description": "string",
        "compatible_locations": "list",
        "size": "string",
        "temperature_min": "integer",
        "temperature_max": "integer",
        "temperature_ideal": "integer",
        "watering_method_preference": "string",
        "drought_tolerance": "integer",
        "overwatering_sensitivity": "integer",
        "soil_preference": "string",
        "soil_replacement_days": "integer",
        "fertilizer_days": "integer",
        "functions": "list",
        "growth_rate_days": "integer",
        "toxic_to_pets": "boolean",
        "propagation_methods": "list",
        "common_pests": "list",
        "image_url": "string",
        "product_ids": "list",
        "care_history": "dict",
        "perenual_id": "string",
        "perenual_verified": "boolean",
        "created_at": "string",
        "updated_at": "string",
        "is_premium_content": "boolean",
        "searchable_text": "string",
        "last_updated": "string"
    }


def get_expected_product_types() -> Dict[str, str]:
    """Get expected data types for product fields"""
    return {
        "id": "string",
        "name": "string",
        "category": "string",
        "subcategory": "string",
        "price": "float",
        "amazon_link": "string",
        "description": "string",
        "compatible_locations": "list",
        "size_compatibility": "string",
        "replacement_days": "integer",
        "application_frequency_days": "integer",
        "plant_ids": "list",
        "watering_method": "string",
        "temperature_control_range": "string",
        "average_rating": "float",
        "review_count": "integer",
        "in_stock": "boolean",
        "image_url": "string",
        "created_at": "string",
        "updated_at": "string",
        "is_premium_content": "boolean",
        "searchable_text": "string"
    }


def get_expected_kit_types() -> Dict[str, str]:
    """Get expected data types for kit fields"""
    return {
        "id": "string",
        "name": "string",
        "locations": "list",
        "natural_light_conditions": "string",
        "led_light_conditions": "string",
        "humidity_level": "string",
        "size_constraint": "string",
        "difficulty": "string",
        "temperature_range": "string",
        "watering_frequency_days": "integer",
        "watering_method": "string",
        "plant_ids": "list",
        "required_product_categories": "list",
        "soil_maintenance_days": "integer",
        "fertilizer_days": "integer",
        "functions": "list",
        "price": "float",
        "difficulty_explanation": "string",
        "setup_time_minutes": "integer",
        "maintenance_time_minutes_weekly": "integer",
        "image_url": "string",
        "created_at": "string",
        "updated_at": "string",
        "is_premium_content": "boolean",
        "searchable_text": "string"
    }


def get_expected_user_types() -> Dict[str, str]:
    """Get expected data types for user fields"""
    return {
        "id": "string",
        "email": "string",
        "subscription_status": "string",
        "plants_owned": "list",
        "kits_owned": "list",
        "custom_configurations": "dict",
        "care_history": "dict",
        "experience_level": "string",
        "join_date": "string",
        "last_login": "string",
        "notification_preferences": "dict",
        "room_conditions": "dict",
        "created_at": "string",
        "updated_at": "string"
    }


def get_expected_plant_product_types() -> Dict[str, str]:
    """Get expected data types for plant-product junction table"""
    return {
        "plant_id": "string",
        "plant_name": "string",
        "product_id": "string",
        "product_name": "string",
        "compatibility_rating": "integer",
        "primary_purpose": "string",
        "recommended_usage": "string",
        "compatibility_notes": "string"
    }


def get_expected_user_plant_types() -> Dict[str, str]:
    """Get expected data types for user-plant junction table"""
    return {
        "user_id": "string",
        "plant_id": "string",
        "nickname": "string",
        "acquisition_date": "string",
        "last_watered": "string",
        "last_fertilized": "string",
        "health_status": "string",
        "location_in_home": "string",
        "days_since_watered": "integer"
    }


def get_required_plant_fields() -> List[str]:
    """Get list of required fields for plants"""
    return [
        "id",
        "name",
        "scientific_name",
        "natural_sunlight_needs",
        "led_light_requirements",
        "water_frequency_days",
        "humidity_preference",
        "difficulty"
    ]


def get_required_product_fields() -> List[str]:
    """Get list of required fields for products"""
    return [
        "id",
        "name",
        "category",
        "price",
        "description"
    ]


def get_required_kit_fields() -> List[str]:
    """Get list of required fields for kits"""
    return [
        "id",
        "name",
        "locations",
        "plant_ids",
        "difficulty",
        "price"
    ]


def get_required_user_fields() -> List[str]:
    """Get list of required fields for users"""
    return [
        "id",
        "email",
        "subscription_status"
    ]


def get_required_plant_product_fields() -> List[str]:
    """Get list of required fields for plant-product relationships"""
    return [
        "plant_id",
        "product_id",
        "compatibility_rating",
        "primary_purpose"
    ]


def get_required_user_plant_fields() -> List[str]:
    """Get list of required fields for user-plant relationships"""
    return [
        "user_id",
        "plant_id",
        "acquisition_date",
        "health_status",
        "location_in_home"
    ]


def process_plant_data(raw_plants_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process raw plant data from Google Sheets.

    Args:
        raw_plants_data (list): List of dictionaries containing raw plant data

    Returns:
        list: List of processed plant data dictionaries
    """
    processed_plants = []
    expected_types = get_expected_plant_types()
    required_fields = get_required_plant_fields()

    for idx, raw_plant in enumerate(raw_plants_data):
        try:
            # Parse and convert data types
            plant = parse_sheet_data(raw_plant, expected_types)

            # Validate required fields
            missing_fields = validate_required_fields(plant, required_fields)
            if missing_fields:
                logger.warning(f"Plant at index {idx} missing required fields: {missing_fields}")
                continue

            processed_plants.append(plant)

        except Exception as e:
            logger.error(f"Error processing plant at index {idx}: {str(e)}")

    logger.info(f"Processed {len(processed_plants)} plants out of {len(raw_plants_data)}")
    return processed_plants


def process_product_data(raw_products_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process raw product data from Google Sheets.

    Args:
        raw_products_data (list): List of dictionaries containing raw product data

    Returns:
        list: List of processed product data dictionaries
    """
    processed_products = []
    expected_types = get_expected_product_types()
    required_fields = get_required_product_fields()

    for idx, raw_product in enumerate(raw_products_data):
        try:
            product = parse_sheet_data(raw_product, expected_types)
            missing_fields = validate_required_fields(product, required_fields)
            if missing_fields:
                logger.warning(f"Product at index {idx} missing required fields: {missing_fields}")
                continue
            processed_products.append(product)
        except Exception as e:
            logger.error(f"Error processing product at index {idx}: {str(e)}")

    logger.info(f"Processed {len(processed_products)} products out of {len(raw_products_data)}")
    return processed_products


def process_kit_data(raw_kits_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process raw kit data from Google Sheets.

    Args:
        raw_kits_data (list): List of dictionaries containing raw kit data

    Returns:
        list: List of processed kit data dictionaries
    """
    processed_kits = []
    expected_types = get_expected_kit_types()
    required_fields = get_required_kit_fields()

    for idx, raw_kit in enumerate(raw_kits_data):
        try:
            kit = parse_sheet_data(raw_kit, expected_types)
            missing_fields = validate_required_fields(kit, required_fields)
            if missing_fields:
                logger.warning(f"Kit at index {idx} missing required fields: {missing_fields}")
                continue
            processed_kits.append(kit)
        except Exception as e:
            logger.error(f"Error processing kit at index {idx}: {str(e)}")

    logger.info(f"Processed {len(processed_kits)} kits out of {len(raw_kits_data)}")
    return processed_kits


def process_user_data(raw_users_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process raw user data from Google Sheets.

    Args:
        raw_users_data (list): List of dictionaries containing raw user data

    Returns:
        list: List of processed user data dictionaries
    """
    processed_users = []
    expected_types = get_expected_user_types()
    required_fields = get_required_user_fields()

    for idx, raw_user in enumerate(raw_users_data):
        try:
            user = parse_sheet_data(raw_user, expected_types)
            missing_fields = validate_required_fields(user, required_fields)
            if missing_fields:
                logger.warning(f"User at index {idx} missing required fields: {missing_fields}")
                continue
            processed_users.append(user)
        except Exception as e:
            logger.error(f"Error processing user at index {idx}: {str(e)}")

    logger.info(f"Processed {len(processed_users)} users out of {len(raw_users_data)}")
    return processed_users


def process_plant_product_data(raw_junction_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process raw plant-product junction data from Google Sheets.

    Args:
        raw_junction_data (list): List of dictionaries containing raw junction data

    Returns:
        list: List of processed junction data dictionaries
    """
    processed_junctions = []
    expected_types = get_expected_plant_product_types()
    required_fields = get_required_plant_product_fields()

    for idx, raw_junction in enumerate(raw_junction_data):
        try:
            junction = parse_sheet_data(raw_junction, expected_types)
            missing_fields = validate_required_fields(junction, required_fields)
            if missing_fields:
                logger.warning(f"Plant-Product junction at index {idx} missing required fields: {missing_fields}")
                continue
            processed_junctions.append(junction)
        except Exception as e:
            logger.error(f"Error processing plant-product junction at index {idx}: {str(e)}")

    logger.info(f"Processed {len(processed_junctions)} plant-product junctions out of {len(raw_junction_data)}")
    return processed_junctions


def process_user_plant_data(raw_junction_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process raw user-plant junction data from Google Sheets.

    Args:
        raw_junction_data (list): List of dictionaries containing raw junction data

    Returns:
        list: List of processed junction data dictionaries
    """
    processed_junctions = []
    expected_types = get_expected_user_plant_types()
    required_fields = get_required_user_plant_fields()

    for idx, raw_junction in enumerate(raw_junction_data):
        try:
            junction = parse_sheet_data(raw_junction, expected_types)
            missing_fields = validate_required_fields(junction, required_fields)
            if missing_fields:
                logger.warning(f"User-Plant junction at index {idx} missing required fields: {missing_fields}")
                continue
            processed_junctions.append(junction)
        except Exception as e:
            logger.error(f"Error processing user-plant junction at index {idx}: {str(e)}")

    logger.info(f"Processed {len(processed_junctions)} user-plant junctions out of {len(raw_junction_data)}")
    return processed_junctions


def prepare_plant_for_api(plant_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare plant data for API consumption by sanitizing and formatting.

    Args:
        plant_data (dict): The processed plant data

    Returns:
        dict: API-ready plant data
    """
    # Create a copy to avoid modifying the original
    api_plant = plant_data.copy()

    # Remove internal fields not needed for API
    internal_fields = ['perenual_verified', 'care_history', 'created_at', 'updated_at']
    for field in internal_fields:
        if field in api_plant:
            del api_plant[field]

    # Format temperature values for consistent API response
    if 'temperature_min' in api_plant and 'temperature_max' in api_plant:
        api_plant['temperature_range'] = f"{api_plant['temperature_min']}°F - {api_plant['temperature_max']}°F"

    # Convert numeric difficulty to text label for better user experience
    if 'difficulty' in api_plant:
        difficulty_level = api_plant['difficulty']
        if difficulty_level <= 3:
            api_plant['difficulty_label'] = 'Easy'
        elif difficulty_level <= 6:
            api_plant['difficulty_label'] = 'Moderate'
        else:
            api_plant['difficulty_label'] = 'Difficult'

    return api_plant


def prepare_product_for_api(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare product data for API consumption by sanitizing and formatting.

    Args:
        product_data (dict): The processed product data

    Returns:
        dict: API-ready product data
    """
    api_product = product_data.copy()

    # Remove internal fields not needed for API
    internal_fields = ['created_at', 'updated_at']
    for field in internal_fields:
        if field in api_product:
            del api_product[field]

    # Format price for display
    if 'price' in api_product:
        api_product['price_display'] = f"${api_product['price']:.2f}"

    return api_product


def prepare_kit_for_api(kit_data: Dict[str, Any], user_tier: str) -> Dict[str, Any]:
    """
    Prepare kit data for API consumption with tier-specific pricing.

    Args:
        kit_data (dict): The processed kit data
        user_tier (str): The user's subscription tier

    Returns:
        dict: API-ready kit data with appropriate pricing
    """
    api_kit = kit_data.copy()

    # Remove internal fields
    internal_fields = ['created_at', 'updated_at']
    for field in internal_fields:
        if field in api_kit:
            del api_kit[field]

    # Calculate tier-specific pricing
    if 'price' in api_kit:
        api_kit['original_price'] = api_kit['price']
        api_kit['price'] = calculate_kit_price(api_kit['price'], user_tier)
        api_kit['price_display'] = f"${api_kit['price']:.2f}"

    # Add tier-specific flags
    api_kit['can_be_saved'] = (user_tier == SUBSCRIPTION_TIERS["SUBSCRIBER"])

    # Check if premium content is accessible based on tier
    if api_kit.get('is_premium_content', False) and user_tier != SUBSCRIPTION_TIERS["SUBSCRIBER"]:
        api_kit['requires_subscription'] = True

    return api_kit


def prepare_user_data_for_sync(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare user data for synchronization with external systems by removing sensitive info.

    Args:
        user_data (dict): Complete user data

    Returns:
        dict: User data ready for sync with sensitive fields removed
    """
    sync_data = user_data.copy()

    # Remove sensitive information
    sensitive_fields = ['email', 'notification_preferences']
    for field in sensitive_fields:
        if field in sync_data:
            sync_data[field] = None

    return sync_data


def get_compatible_products_for_plant(plant_id: str, plant_product_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Get compatible products for a specific plant based on junction table data.

    Args:
        plant_id (str): ID of the plant
        plant_product_data (list): List of plant-product junction data

    Returns:
        list: List of compatible product entries with compatibility details
    """
    compatible_products = []

    for junction in plant_product_data:
        if junction.get('plant_id') == plant_id:
            compatible_products.append(junction)

    # Sort by compatibility rating (highest first)
    return sorted(compatible_products, key=lambda x: x.get('compatibility_rating', 0), reverse=True)


def get_user_plants(user_id: str, user_plant_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Get plants owned by a specific user based on junction table data.

    Args:
        user_id (str): ID of the user
        user_plant_data (list): List of user-plant junction data

    Returns:
        list: List of user's plants with personal details
    """
    user_plants = []

    for junction in user_plant_data:
        if junction.get('user_id') == user_id:
            user_plants.append(junction)

    # Sort by acquisition date (newest first) if available
    return sorted(user_plants,
                  key=lambda x: x.get('acquisition_date', ''),
                  reverse=True)