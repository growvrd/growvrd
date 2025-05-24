"""
GrowVRD Recommendation Engine

This module provides plant and product recommendation functionality
with subscription-aware features, analytics, and personalized care schedules.
"""
import logging
import functools
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import (
    List, Dict, Any, Optional, Set, Union, Tuple, TypedDict,
    Literal, Protocol, cast, overload
)
from datetime import datetime, timedelta
from enum import Enum, auto

# Import from your core modules
from core.oauth_sheets_connector import (
    get_plants_data, get_products_data, get_kits_data, get_users_data,
    get_plant_products_data, get_user_plants_data, update_user_kit, get_user_by_email,
    GoogleSheetsDataError
)
from core.data_handler import (
    parse_sheet_data, get_expected_plant_types, get_expected_product_types,
    get_expected_kit_types, process_plant_data, process_product_data, process_kit_data
)
from core.filters import (
    filter_plants, filter_by_location, filter_by_difficulty, filter_by_maintenance,
    filter_by_function, filter_by_light_wattage, filter_by_temperature, filter_by_humidity,
    filter_by_light_requirements, rank_plants, filter_plants_by_subscription
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('recommendation_engine')

# Simple in-memory cache
_cache = {}


# -------------------------------------------------------------------------------
# Type definitions for improved type checking
# -------------------------------------------------------------------------------

# Subscription tiers
class SubscriptionTier(str, Enum):
    FREE = "free"
    SUBSCRIBER = "subscriber"
    PREMIUM = "premium"  # Future extension possibility


# Experience levels
class ExperienceLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# Maintenance preferences
class MaintenanceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Light conditions
class LightCondition(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    BRIGHT_INDIRECT = "bright_indirect"
    DIRECT = "direct"


# Plant health status
class PlantHealthStatus(str, Enum):
    HEALTHY = "healthy"
    NEEDS_ATTENTION = "needs_attention"
    DECLINING = "declining"
    RECOVERING = "recovering"


# Type definitions for data structures
class PlantDict(TypedDict, total=False):
    id: str
    name: str
    scientific_name: str
    led_light_requirements: str
    natural_sunlight_needs: str
    natural_sunlight_required: bool
    recommended_light_wattage: int
    led_wattage_min: int
    led_wattage_max: int
    water_frequency_days: int
    humidity_preference: str
    difficulty: int
    maintenance: str
    indoor_compatible: bool
    description: str
    compatible_locations: List[str]
    size: str
    temperature_min: int
    temperature_max: int
    temperature_ideal: int
    watering_method_preference: str
    drought_tolerance: int
    overwatering_sensitivity: int
    soil_preference: str
    soil_replacement_days: int
    fertilizer_days: int
    functions: List[str]
    growth_rate_days: int
    toxic_to_pets: bool
    propagation_methods: List[str]
    common_pests: List[str]
    image_url: str
    product_ids: List[str]
    care_history: Dict[str, Any]
    is_premium_content: bool
    match_score: float  # Added during ranking
    normalized_score: float  # Added during ranking
    score_components: Dict[str, float]  # Added during ranking


class ProductDict(TypedDict, total=False):
    id: str
    name: str
    category: str
    subcategory: str
    price: float
    amazon_link: str
    description: str
    compatible_locations: List[str]
    size_compatibility: str
    replacement_days: int
    application_frequency_days: int
    plant_ids: List[str]
    watering_method: str
    temperature_control_range: str
    average_rating: float
    review_count: int
    in_stock: bool
    image_url: str
    relevance_score: float  # Added during recommendation
    relevance_reasons: List[str]  # Added during recommendation
    base_price: float  # Added during pricing calculation
    service_fee: float  # Added during pricing calculation
    adjusted_price: float  # Added during pricing calculation
    subscriber_savings: float  # Added for subscribers


class KitDict(TypedDict, total=False):
    id: str
    name: str
    locations: List[str]
    natural_light_conditions: str
    led_light_conditions: str
    humidity_level: str
    size_constraint: str
    difficulty: Union[int, str]
    temperature_range: str
    watering_frequency_days: int
    watering_method: str
    plant_ids: List[str]
    required_product_categories: List[str]
    soil_maintenance_days: int
    fertilizer_days: int
    functions: List[str]
    price: float
    difficulty_explanation: str
    setup_time_minutes: int
    maintenance_time_minutes_weekly: int
    image_url: str
    relevance_score: float  # Added during recommendation
    relevance_reasons: List[str]  # Added during recommendation
    is_premium_content: bool


class UserPreferencesDict(TypedDict, total=False):
    location: str
    experience_level: str
    maintenance: str
    functions: List[str]
    light: str
    light_wattage: float
    temperature: float
    humidity: float
    size_constraint: str
    is_subscriber: bool
    max_plants: int
    max_products: int
    max_kits: int
    weights: Dict[str, float]  # For custom ranking weights


class LightAnalysisDict(TypedDict):
    plant_name: str
    required_wattage: float
    available_wattage: float
    light_requirements: str
    is_sufficient: Optional[bool]
    wattage_gap: Optional[float]
    recommendation: str


class CareTaskDict(TypedDict):
    plant: str
    task: str
    details: str
    due_date: Optional[str]  # ISO format date


class CareScheduleDict(TypedDict):
    daily: List[CareTaskDict]
    weekly: List[CareTaskDict]
    monthly: List[CareTaskDict]
    quarterly: List[CareTaskDict]
    annually: List[CareTaskDict]


class AnalyticsDict(TypedDict):
    available: bool
    basic: Dict[str, Any]
    detailed: Optional[Dict[str, Any]]
    upgrade_message: Optional[str]


class RecommendationResponseDict(TypedDict):
    plants: List[PlantDict]
    products: List[ProductDict]
    kits: List[KitDict]
    care_schedule: CareScheduleDict
    light_analysis: List[LightAnalysisDict]
    analytics: AnalyticsDict
    stats: Dict[str, Any]
    subscription_tier: str
    subscriber_features: Dict[str, Any]
    custom_kit: Optional[Dict[str, Any]]
    error: Optional[str]
    message: Optional[str]


# -------------------------------------------------------------------------------
# Custom exceptions
# -------------------------------------------------------------------------------

class RecommendationError(Exception):
    """Exception raised for errors in the recommendation process"""
    pass


class QuotaExceededError(RecommendationError):
    """Exception raised when user has exceeded their recommendation quota"""
    pass


class InvalidPreferenceError(RecommendationError):
    """Exception raised when user preferences are invalid"""
    pass


class DataRetrievalError(RecommendationError):
    """Exception raised when data retrieval fails"""
    pass


# -------------------------------------------------------------------------------
# Data retrieval and processing
# -------------------------------------------------------------------------------


def get_data_from_sheets() -> Tuple[List[PlantDict], List[ProductDict], List[KitDict]]:
    """
    Retrieve and process all necessary data from Google Sheets using optimized batch access.

    Returns:
        Tuple containing plants, products, and kits data

    Raises:
        DataRetrievalError: If data retrieval fails
    """
    try:
        # Use the optimized batch function
        from core.oauth_sheets_connector import get_all_data

        try:
            # Try to get data in a batch to reduce API calls
            plants_data, products_data, kits_data = get_all_data()
            logger.info("Successfully retrieved data in batch mode")
        except (ImportError, AttributeError):
            # Fall back to individual calls if batch function is not available
            logger.info("Batch retrieval not available, using individual calls")
            plants_data = get_plants_data()
            products_data = get_products_data()
            kits_data = get_kits_data()

        # Process data using data_handler functions
        processed_plants = process_plant_data(plants_data)
        processed_products = process_product_data(products_data)
        processed_kits = process_kit_data(kits_data)

        logger.info(f"Successfully retrieved data: {len(processed_plants)} plants, "
                    f"{len(processed_products)} products, {len(processed_kits)} kits")

        # Cast to correct types
        return (
            cast(List[PlantDict], processed_plants),
            cast(List[ProductDict], processed_products),
            cast(List[KitDict], processed_kits)
        )

    except GoogleSheetsDataError as e:
        error_msg = f"Failed to retrieve data from Google Sheets: {str(e)}"
        logger.error(error_msg)
        raise DataRetrievalError(error_msg)
    except Exception as e:
        error_msg = f"Error retrieving or processing data: {str(e)}"
        logger.error(error_msg)
        raise DataRetrievalError(error_msg)


# -------------------------------------------------------------------------------
# Subscription service
# -------------------------------------------------------------------------------

class SubscriptionService:
    """Service to handle subscription-related functionality"""

    # Rate limits by tier
    RATE_LIMITS = {
        SubscriptionTier.FREE: {'daily': 10, 'monthly': 100},
        SubscriptionTier.SUBSCRIBER: {'daily': 50, 'monthly': 1000},
        SubscriptionTier.PREMIUM: {'daily': 100, 'monthly': 2000},
    }

    # Service fees by tier
    SERVICE_FEES = {
        SubscriptionTier.FREE: 0.10,  # 10%
        SubscriptionTier.SUBSCRIBER: 0.03,  # 3%
        SubscriptionTier.PREMIUM: 0.00,  # 0%
    }

    # Feature flags by tier
    FEATURES = {
        SubscriptionTier.FREE: {
            'can_save_custom_kits': False,
            'detailed_analytics': False,
            'unlimited_plants': False,
            'priority_support': False,
        },
        SubscriptionTier.SUBSCRIBER: {
            'can_save_custom_kits': True,
            'detailed_analytics': True,
            'unlimited_plants': False,
            'priority_support': False,
        },
        SubscriptionTier.PREMIUM: {
            'can_save_custom_kits': True,
            'detailed_analytics': True,
            'unlimited_plants': True,
            'priority_support': True,
        }
    }

    @staticmethod
    def get_user_tier(email: Optional[str] = None) -> SubscriptionTier:
        """
        Get the subscription tier for a user.

        Args:
            email: User's email address

        Returns:
            SubscriptionTier enum value
        """
        if not email:
            return SubscriptionTier.FREE

        try:
            user = get_user_by_email(email)
            if not user:
                return SubscriptionTier.FREE

            status = user.get('subscription_status', '').lower()
            if status == 'subscriber':
                return SubscriptionTier.SUBSCRIBER
            elif status == 'premium':
                return SubscriptionTier.PREMIUM
            else:
                return SubscriptionTier.FREE
        except Exception as e:
            logger.warning(f"Error getting subscription status for {email}: {str(e)}")
            return SubscriptionTier.FREE

    @staticmethod
    def check_quota(email: str, tier: Optional[SubscriptionTier] = None) -> Tuple[bool, str]:
        """
        Check if user has exceeded their recommendation quota.

        Args:
            email: User's email address
            tier: User's subscription tier (will be looked up if not provided)

        Returns:
            Tuple of (has_quota_remaining, message)
        """
        try:
            # Get tier if not provided
            if tier is None:
                tier = SubscriptionService.get_user_tier(email)

            user = get_user_by_email(email)
            if not user:
                # Create default tracking for new users
                today = datetime.now().date().isoformat()
                request_tracking = {
                    'last_reset_date': today,
                    'daily_count': 1,
                    'monthly_count': 1
                }
                return True, "First request today"

            # Get or initialize request tracking
            request_tracking = user.get('request_tracking', {})
            if not isinstance(request_tracking, dict):
                request_tracking = {}

            # Check if we need to reset counters
            today = datetime.now().date().isoformat()
            last_reset = request_tracking.get('last_reset_date', today)

            if last_reset != today:
                # Reset daily counter for a new day
                request_tracking['daily_count'] = 0
                request_tracking['last_reset_date'] = today

            # Increment counters
            daily_count = request_tracking.get('daily_count', 0) + 1
            monthly_count = request_tracking.get('monthly_count', 0) + 1

            # Get limits for the tier
            limits = SubscriptionService.RATE_LIMITS.get(tier, SubscriptionService.RATE_LIMITS[SubscriptionTier.FREE])
            daily_limit = limits['daily']
            monthly_limit = limits['monthly']

            # Check if user has exceeded limits
            if daily_count > daily_limit:
                return False, f"Daily recommendation limit of {daily_limit} exceeded"

            if monthly_count > monthly_limit:
                return False, f"Monthly recommendation limit of {monthly_limit} exceeded"

            # Update tracking
            request_tracking['daily_count'] = daily_count
            request_tracking['monthly_count'] = monthly_count

            # Here you would update the user's tracking info in the database
            # update_user_request_tracking(user_email, request_tracking)

            return True, "Quota available"

        except Exception as e:
            logger.error(f"Error checking recommendation quota: {str(e)}")
            # On error, allow the request to proceed
            return True, "Quota check error, proceeding anyway"

    @staticmethod
    def can_access_feature(feature: str, tier: SubscriptionTier) -> bool:
        """
        Check if a tier has access to a specific feature.

        Args:
            feature: Feature name
            tier: Subscription tier

        Returns:
            True if the tier has access to the feature
        """
        tier_features = SubscriptionService.FEATURES.get(tier, {})
        return tier_features.get(feature, False)

    @staticmethod
    def calculate_service_fee(base_price: float, tier: SubscriptionTier) -> float:
        """
        Calculate service fee based on subscription tier.

        Args:
            base_price: Base price
            tier: Subscription tier

        Returns:
            Service fee amount
        """
        fee_percentage = SubscriptionService.SERVICE_FEES.get(tier, 0.10)
        return base_price * fee_percentage


# -------------------------------------------------------------------------------
# Product recommendation logic
# -------------------------------------------------------------------------------

def match_products_to_plants(
        plants: List[PlantDict],
        products_data: List[ProductDict],
        plant_product_data: Optional[List[Dict[str, Any]]] = None
) -> List[ProductDict]:
    """
    Match suitable products to selected plants with improved logic and junction table support.

    Args:
        plants: List of selected plant dictionaries
        products_data: List of product dictionaries
        plant_product_data: Optional pre-loaded plant-product relationships

    Returns:
        List of recommended products with relevance scores
    """
    if not plants or not products_data:
        logger.warning("Empty plants or products data provided to match_products_to_plants")
        return []

    # Load plant-product relationships if not provided
    if plant_product_data is None:
        try:
            plant_product_data = get_plant_products_data()
        except Exception as e:
            logger.warning(f"Failed to get plant-product relationships: {str(e)}")
            plant_product_data = []

    # Build lookup dictionary for plant-product relationships
    plant_product_map: Dict[str, List[Dict[str, Any]]] = {}
    for relation in plant_product_data:
        plant_id = relation.get('plant_id', '')
        if plant_id:
            if plant_id not in plant_product_map:
                plant_product_map[plant_id] = []
            plant_product_map[plant_id].append(relation)

    recommended_products = []
    needed_categories: Set[str] = set()
    plant_specific_products: Dict[str, List[Dict[str, Any]]] = {}

    # Determine needed product categories based on plants
    for plant in plants:
        plant_name = plant.get('name', 'Unknown Plant')
        plant_id = plant.get('id', '')

        # Check light requirements
        led_light_reqs = plant.get('led_light_requirements', '')
        if isinstance(led_light_reqs, list):
            if any('low' in str(req).lower() for req in led_light_reqs):
                needed_categories.add('grow_light')
        elif isinstance(led_light_reqs, str) and 'low' in led_light_reqs.lower():
            needed_categories.add('grow_light')

        # Check water frequency
        water_freq = plant.get('water_frequency_days', 0)
        try:
            water_freq = int(water_freq)
            if water_freq <= 3:  # Needs watering multiple times per week
                needed_categories.add('watering_system')
        except (ValueError, TypeError):
            # Handle string values
            if isinstance(water_freq, str) and any(term in water_freq.lower()
                                                   for term in ['frequent', 'daily', 'high']):
                needed_categories.add('watering_system')

        # Check humidity preference
        humidity = plant.get('humidity_preference', '')
        if isinstance(humidity, str) and 'high' in humidity.lower():
            needed_categories.add('humidifier')

        # Check temperature requirements
        temp_min = plant.get('temperature_min', 0)
        temp_max = plant.get('temperature_max', 100)
        try:
            temp_range = abs(float(temp_max) - float(temp_min))
            if temp_range < 15:  # Narrow temperature range
                needed_categories.add('temperature_control')
        except (ValueError, TypeError):
            pass

        # Always include basic categories
        needed_categories.add('pot')
        needed_categories.add('soil')

        # Check for plant-specific product compatibility from junction table
        if plant_id in plant_product_map:
            plant_specific_products[plant_id] = plant_product_map[plant_id]

    scored_products = []

    # Score and select products that match needed categories
    for product in products_data:
        product_id = product.get('id', '')
        category = product.get('category', '').lower()
        subcategory = product.get('subcategory', '').lower()

        if not category:
            continue

        score = 0
        relevance_reasons = []

        # Score based on needed categories
        if category in needed_categories:
            score += 10
            relevance_reasons.append(f"Matches needed category: {category}")

        # Check for compatibility from plant-product junction table
        junction_compatibility_found = False
        compatibility_ratings = []

        for plant_id, relations in plant_specific_products.items():
            for relation in relations:
                if relation.get('product_id') == product_id:
                    rating = relation.get('compatibility_rating', 0)
                    try:
                        rating = int(rating)
                        compatibility_ratings.append(rating)
                    except (ValueError, TypeError):
                        pass

                    purpose = relation.get('primary_purpose', '')
                    if purpose:
                        relevance_reasons.append(f"Used for {purpose}")

                    notes = relation.get('compatibility_notes', '')
                    if notes:
                        relevance_reasons.append(f"Note: {notes}")

                    junction_compatibility_found = True

        # Add compatibility score from junction table
        if compatibility_ratings:
            avg_rating = sum(compatibility_ratings) / len(compatibility_ratings)
            score += avg_rating * 3  # Weight compatibility ratings heavily
            relevance_reasons.append(f"Average compatibility rating: {avg_rating:.1f}/5")

        # Check product price range (prefer mid-range products)
        try:
            price = float(product.get('price', 0))
            if 10 <= price <= 50:
                score += 5
                relevance_reasons.append("Reasonable price range")
            elif price > 50:
                score -= 3
                relevance_reasons.append("Premium product")
        except (ValueError, TypeError):
            pass

        # Add product with its score if it's relevant
        if score > 0 or junction_compatibility_found:
            product_copy = cast(ProductDict, product.copy())
            product_copy['relevance_score'] = score
            product_copy['relevance_reasons'] = relevance_reasons
            scored_products.append(product_copy)

    # Sort by relevance score (highest first)
    recommended_products = sorted(scored_products, key=lambda p: p.get('relevance_score', 0), reverse=True)

    logger.debug(f"Matched {len(recommended_products)} products to {len(plants)} plants")
    return recommended_products


# -------------------------------------------------------------------------------
# Kit recommendation logic
# -------------------------------------------------------------------------------

def find_matching_kits(
        location: Optional[str],
        kits_data: List[KitDict],
        user_preferences: UserPreferencesDict
) -> List[KitDict]:
    """
    Find pre-defined kits that match user criteria with enhanced scoring.

    Args:
        location: Room location
        kits_data: List of kit dictionaries
        user_preferences: Dict containing user preferences

    Returns:
        List of recommended kits with relevance scores
    """
    if not kits_data:
        logger.warning("Empty kits data provided to find_matching_kits")
        return []

    if not location:
        logger.warning("No location provided to find_matching_kits")
        return []

    matching_kits = []
    difficulty = user_preferences.get('experience_level')
    light_conditions = user_preferences.get('light')
    humidity_level = user_preferences.get('humidity')
    size_constraint = user_preferences.get('size_constraint')

    for kit in kits_data:
        # Calculate a relevance score for this kit
        score = 0
        relevance_reasons = []

        # Check location match
        kit_locations = kit.get('locations', [])
        if isinstance(kit_locations, str):
            kit_locations = [loc.strip() for loc in kit_locations.split(',')]

        location_match = any(str(loc).lower() == location.lower() for loc in kit_locations)
        if location_match:
            score += 10
            relevance_reasons.append(f"Designed for {location}")
        else:
            # If location doesn't match, skip this kit entirely
            continue

        # Check difficulty match
        if difficulty:
            kit_difficulty = kit.get('difficulty', '')

            if isinstance(kit_difficulty, (int, float)):
                # Numeric difficulty
                user_diff_map = {'beginner': 2, 'intermediate': 3, 'advanced': 5}
                user_diff_value = user_diff_map.get(str(difficulty).lower(), 3)

                if kit_difficulty <= user_diff_value:
                    score += 8
                    relevance_reasons.append(f"Matches {difficulty} experience level")
            else:
                # String difficulty
                kit_difficulty = str(kit_difficulty).lower()

                if str(difficulty).lower() == 'beginner' and any(d in kit_difficulty for d in ['easy', 'beginner']):
                    score += 8
                    relevance_reasons.append("Suitable for beginners")
                elif str(difficulty).lower() == 'intermediate' and any(
                        d in kit_difficulty for d in ['moderate', 'intermediate']):
                    score += 8
                    relevance_reasons.append("Suitable for intermediate gardeners")
                elif str(difficulty).lower() == 'advanced' and any(
                        d in kit_difficulty for d in ['difficult', 'advanced']):
                    score += 8
                    relevance_reasons.append("Suitable for advanced gardeners")

        # Check light conditions match
        if light_conditions:
            kit_light = kit.get('led_light_conditions', '')
            if str(kit_light).lower() == str(light_conditions).lower():
                score += 6
                relevance_reasons.append(f"Designed for {light_conditions} light conditions")

        # Check size constraints
        if size_constraint:
            kit_size = kit.get('size_constraint', '')
            if str(kit_size).lower() == str(size_constraint).lower():
                score += 5
                relevance_reasons.append(f"Fits your {size_constraint} space constraint")

        # Check plant contents
        kit_plants = kit.get('plant_ids', [])
        if isinstance(kit_plants, str):
            kit_plants = [p.strip() for p in kit_plants.split(',')]

        if kit_plants:
            score += 3
            relevance_reasons.append(f"Includes {len(kit_plants)} plants")

        # Add kit with its score if relevant
        if score >= 10:  # Must at least match the location
            kit_copy = cast(KitDict, kit.copy())
            kit_copy['relevance_score'] = score
            kit_copy['relevance_reasons'] = relevance_reasons
            matching_kits.append(kit_copy)

    # Sort by relevance score (highest first)
    matching_kits = sorted(matching_kits, key=lambda k: k.get('relevance_score', 0), reverse=True)

    logger.debug(f"Found {len(matching_kits)} matching kits for location '{location}'")
    return matching_kits


# -------------------------------------------------------------------------------
# Pricing and calculation utilities
# -------------------------------------------------------------------------------

def calculate_pricing(
        item: Union[ProductDict, KitDict],
        tier: SubscriptionTier = SubscriptionTier.FREE
) -> Union[ProductDict, KitDict]:
    """
    Calculate pricing with appropriate service fees based on subscription tier.

    Args:
        item: Product or kit with 'price' field
        tier: User's subscription tier

    Returns:
        Item with added pricing fields
    """
    updated_item = item.copy()

    try:
        if 'price' in item:
            base_price = float(item['price'])

            # Apply service fee from subscription service
            service_fee_percentage = SubscriptionService.SERVICE_FEES.get(tier, 0.10)
            service_fee = base_price * service_fee_percentage

            # Round to 2 decimal places
            updated_item['base_price'] = base_price
            updated_item['service_fee'] = round(service_fee, 2)
            updated_item['service_fee_percentage'] = service_fee_percentage * 100
            updated_item['adjusted_price'] = round(base_price + service_fee, 2)

            # Calculate savings for subscribers
            if tier != SubscriptionTier.FREE:
                regular_fee = base_price * 0.10
                savings = regular_fee - service_fee
                updated_item['subscriber_savings'] = round(savings, 2)
    except (ValueError, TypeError) as e:
        logger.warning(f"Error calculating price for item {item.get('name', 'unknown')}: {str(e)}")

    return updated_item


# -------------------------------------------------------------------------------
# Analytics utilities
# -------------------------------------------------------------------------------

def analyze_light_requirements(
        plant: PlantDict,
        available_wattage: Optional[Union[int, float]]
) -> LightAnalysisDict:
    """
    Analyze if available light is sufficient for a plant with enhanced insights.

    Args:
        plant: Plant data dictionary
        available_wattage: User's available light wattage

    Returns:
        Analysis results with sufficiency and recommendations
    """
    plant_name = plant.get('name', 'Unknown')

    if available_wattage is None:
        return {
            'plant_name': plant_name,
            'required_wattage': 0,
            'available_wattage': 0,
            'light_requirements': '',
            'is_sufficient': None,
            'wattage_gap': None,
            'recommendation': "Provide light wattage information for detailed analysis."
        }

    try:
        available_wattage = float(available_wattage)
    except (ValueError, TypeError):
        return {
            'plant_name': plant_name,
            'required_wattage': 0,
            'available_wattage': 0,
            'light_requirements': '',
            'is_sufficient': None,
            'wattage_gap': None,
            'recommendation': "Invalid light wattage value provided."
        }

    try:
        # Use min wattage as primary metric with fallback to recommended
        led_min = float(plant.get('led_wattage_min', 0))
        required_wattage = led_min if led_min > 0 else float(plant.get('recommended_light_wattage', 0))
    except (ValueError, TypeError):
        required_wattage = 0

    # Get light requirements description
    led_light_requirements = plant.get('led_light_requirements', '')
    natural_light_requirements = plant.get('natural_sunlight_needs', '')

    if led_light_requirements and natural_light_requirements:
        light_requirements = f"LED: {led_light_requirements}, Natural: {natural_light_requirements}"
    elif led_light_requirements:
        light_requirements = f"LED: {led_light_requirements}"
    elif natural_light_requirements:
        light_requirements = f"Natural: {natural_light_requirements}"
    else:
        light_requirements = "Not specified"

    # Calculate wattage gap
    is_sufficient = available_wattage >= required_wattage
    wattage_gap = required_wattage - available_wattage if not is_sufficient else 0

    analysis: LightAnalysisDict = {
        'plant_name': plant_name,
        'required_wattage': required_wattage,
        'available_wattage': available_wattage,
        'light_requirements': light_requirements,
        'is_sufficient': is_sufficient,
        'wattage_gap': round(wattage_gap, 1) if wattage_gap > 0 else None
    }

    # Generate recommendations
    if not is_sufficient:
        if wattage_gap <= 10:
            analysis[
                'recommendation'] = f"Add a small grow light with approximately {round(wattage_gap)}W output for optimal growth."
        elif wattage_gap <= 30:
            analysis[
                'recommendation'] = f"Add a medium grow light with approximately {round(wattage_gap)}W output for optimal growth."
        else:
            analysis[
                'recommendation'] = f"Add a larger grow light system with at least {round(wattage_gap)}W output for optimal growth."
    else:
        excess = available_wattage - required_wattage
        if excess > 30:
            analysis['recommendation'] = "Your current lighting is more than sufficient. Consider adding more plants!"
        else:
            analysis['recommendation'] = "Your current lighting is adequate for this plant."

    return analysis


def create_care_schedule(plants: List[PlantDict]) -> CareScheduleDict:
    """
    Create a care schedule for the selected plants with specific dates.

    Args:
        plants: List of plant dictionaries

    Returns:
        Dictionary with care tasks organized by frequency
    """
    if not plants:
        return {
            'daily': [],
            'weekly': [],
            'monthly': [],
            'quarterly': [],
            'annually': []
        }

    schedule = {
        'daily': [],
        'weekly': [],
        'monthly': [],
        'quarterly': [],
        'annually': []
    }

    today = datetime.now()

    for plant in plants:
        plant_name = plant.get('name', 'Unknown plant')

        # Water frequency
        water_frequency = plant.get('water_frequency_days', 0)
        try:
            water_frequency = int(water_frequency)
            water_task: CareTaskDict = {
                'plant': plant_name,
                'task': 'Water plant',
                'details': '',
                'due_date': None
            }

            # Calculate next watering date
            next_water_date = (today + timedelta(days=water_frequency)).strftime('%Y-%m-%d')
            water_task['due_date'] = next_water_date

            # Add watering instructions
            if water_frequency <= 1:
                water_task['details'] = 'Keep soil consistently moist'
                schedule['daily'].append(water_task)
            elif water_frequency <= 3:
                water_task['details'] = f'Water approximately every {water_frequency} days'
                schedule['weekly'].append(water_task)
            elif water_frequency <= 10:
                water_task['details'] = f'Water approximately every {water_frequency} days'
                schedule['weekly'].append(water_task)
            else:
                water_task['details'] = f'Water approximately every {water_frequency} days'
                schedule['monthly'].append(water_task)
        except (ValueError, TypeError):
            # Handle string frequency descriptions
            if isinstance(water_frequency, str):
                task: CareTaskDict = {
                    'plant': plant_name,
                    'task': 'Water plant',
                    'details': str(water_frequency),
                    'due_date': None
                }

                if any(term in str(water_frequency).lower() for term in ['daily', 'everyday']):
                    schedule['daily'].append(task)
                elif any(term in str(water_frequency).lower() for term in ['weekly', 'week']):
                    schedule['weekly'].append(task)
                else:
                    schedule['weekly'].append(task)

        # Fertilizer frequency
        fertilizer_days = plant.get('fertilizer_days', 0)
        try:
            fertilizer_days = int(fertilizer_days)
            if fertilizer_days > 0:
                next_fertilize_date = (today + timedelta(days=fertilizer_days)).strftime('%Y-%m-%d')
                fertilizer_task: CareTaskDict = {
                    'plant': plant_name,
                    'task': 'Apply fertilizer',
                    'details': f'Apply fertilizer approximately every {fertilizer_days} days',
                    'due_date': next_fertilize_date
                }

                if fertilizer_days <= 30:
                    schedule['monthly'].append(fertilizer_task)
                elif fertilizer_days <= 90:
                    schedule['quarterly'].append(fertilizer_task)
                else:
                    schedule['annually'].append(fertilizer_task)
        except (ValueError, TypeError):
            # If fertilizer frequency isn't a valid number, skip
            pass

        # Soil replacement
        soil_replacement_days = plant.get('soil_replacement_days', 0)
        try:
            soil_replacement_days = int(soil_replacement_days)
            if soil_replacement_days > 0:
                next_soil_date = (today + timedelta(days=soil_replacement_days)).strftime('%Y-%m-%d')
                soil_task: CareTaskDict = {
                    'plant': plant_name,
                    'task': 'Replace soil',
                    'details': f'Replace soil approximately every {soil_replacement_days} days',
                    'due_date': next_soil_date
                }
                schedule['annually'].append(soil_task)
        except (ValueError, TypeError):
            # If soil replacement isn't a valid number, skip
            pass

        # Add generic care tasks
        weekly_inspect: CareTaskDict = {
            'plant': plant_name,
            'task': 'Inspect for pests and diseases',
            'details': 'Check leaves and stems for signs of pests or disease',
            'due_date': (today + timedelta(days=7)).strftime('%Y-%m-%d')
        }
        schedule['weekly'].append(weekly_inspect)

        weekly_prune: CareTaskDict = {
            'plant': plant_name,
            'task': 'Remove dead leaves',
            'details': 'Prune any dead or yellowing leaves',
            'due_date': (today + timedelta(days=7)).strftime('%Y-%m-%d')
        }
        schedule['weekly'].append(weekly_prune)

        monthly_clean: CareTaskDict = {
            'plant': plant_name,
            'task': 'Clean leaves',
            'details': 'Gently wipe leaves with a damp cloth to remove dust',
            'due_date': (today + timedelta(days=30)).strftime('%Y-%m-%d')
        }
        schedule['monthly'].append(monthly_clean)

    return schedule


def generate_detailed_analytics(
        plants: List[PlantDict],
        user_preferences: UserPreferencesDict,
        tier: SubscriptionTier
) -> AnalyticsDict:
    """
    Generate detailed plant analytics with tier-specific insights.

    Args:
        plants: List of recommended plants
        user_preferences: User preferences
        tier: User's subscription tier

    Returns:
        Dictionary containing analytics data
    """
    if not plants:
        return {'available': False, 'basic': {}, 'detailed': None, 'upgrade_message': None}

    # Basic analytics available to all users
    basic_analytics = {
        'total_plants': len(plants),
        'difficulty_breakdown': {
            'easy': sum(1 for p in plants if str(p.get('difficulty', '')).lower() in ['1', 'easy', 'beginner']),
            'medium': sum(
                1 for p in plants if str(p.get('difficulty', '')).lower() in ['2', '3', 'medium', 'moderate']),
            'hard': sum(1 for p in plants if
                        str(p.get('difficulty', '')).lower() in ['4', '5', 'hard', 'difficult', 'advanced'])
        },
        'monthly_care_estimate': {
            'watering_events': sum(30 // max(int(p.get('water_frequency_days', 7)), 1) for p in plants),
            'fertilizer_events': sum(1 for p in plants if p.get('fertilizer_days', 0) <= 30)
        }
    }

    # Return only basic analytics for free users
    if tier == SubscriptionTier.FREE:
        return {
            'available': True,
            'basic': basic_analytics,
            'detailed': None,
            'upgrade_message': "Upgrade to subscriber tier for detailed plant analytics and growth predictions."
        }

    # Enhanced analytics for subscribers
    detailed_analytics = {
        'environment_suitability': {},
        'predicted_growth_rate': {},
        'common_issues_risk': {},
        'seasonal_care_adjustments': {}
    }

    # Environment suitability
    if 'temperature' in user_preferences and 'humidity' in user_preferences:
        try:
            room_temp = float(user_preferences.get('temperature', 70))
            room_humidity = float(user_preferences.get('humidity', 50))

            for plant in plants:
                plant_name = plant.get('name', 'Unknown')

                # Temperature suitability
                temp_min = float(plant.get('temperature_min', 0))
                temp_max = float(plant.get('temperature_max', 100))
                temp_ideal = float(plant.get('temperature_ideal', (temp_min + temp_max) / 2))

                # If temp is in range, calculate how close to ideal
                if temp_min <= room_temp <= temp_max:
                    temp_range = (temp_max - temp_min) / 2
                    temp_distance = abs(room_temp - temp_ideal)
                    temp_score = 100 - (temp_distance / temp_range * 100) if temp_range > 0 else 100
                else:
                    temp_score = 0

                # Humidity suitability
                humidity_pref = plant.get('humidity_preference', 'medium').lower()
                humidity_score = 0

                if humidity_pref == 'low' and room_humidity < 40:
                    humidity_score = 100
                elif humidity_pref == 'low' and room_humidity < 60:
                    humidity_score = 70
                elif humidity_pref == 'medium' and 40 <= room_humidity <= 60:
                    humidity_score = 100
                elif humidity_pref == 'medium':
                    humidity_score = 70
                elif humidity_pref == 'high' and room_humidity > 60:
                    humidity_score = 100
                elif humidity_pref == 'high' and room_humidity > 40:
                    humidity_score = 70
                else:
                    humidity_score = 50

                # Overall environmental suitability
                overall_score = (temp_score + humidity_score) / 2
                detailed_analytics['environment_suitability'][plant_name] = round(overall_score)
        except (ValueError, TypeError) as e:
            logger.warning(f"Error calculating environment suitability: {str(e)}")

    # Predicted growth rate (subscribe-only detail)
    for plant in plants:
        plant_name = plant.get('name', 'Unknown')
        growth_rate_days = plant.get('growth_rate_days', 0)

        try:
            growth_rate = int(growth_rate_days)
            if growth_rate > 0:
                if growth_rate < 30:
                    detailed_analytics['predicted_growth_rate'][plant_name] = "Fast (noticeable growth within weeks)"
                elif growth_rate < 90:
                    detailed_analytics['predicted_growth_rate'][plant_name] = "Medium (noticeable growth within months)"
                else:
                    detailed_analytics['predicted_growth_rate'][
                        plant_name] = "Slow (may take 3+ months to see significant growth)"
        except (ValueError, TypeError):
            detailed_analytics['predicted_growth_rate'][plant_name] = "Unknown"

    # Common issues risk assessment
    for plant in plants:
        plant_name = plant.get('name', 'Unknown')
        common_pests = plant.get('common_pests', [])

        if isinstance(common_pests, str):
            common_pests = [p.strip() for p in common_pests.split(',')]

        if common_pests:
            detailed_analytics['common_issues_risk'][plant_name] = {
                'common_pests': common_pests,
                'risk_level': 'High' if len(common_pests) > 2 else 'Medium' if common_pests else 'Low',
                'prevention_tips': [
                    "Regular inspection of leaves and stems",
                    "Maintain proper humidity and airflow",
                    "Isolate new plants for 2 weeks before introducing to your collection"
                ]
            }

    # Seasonal care adjustments
    current_month = datetime.now().month
    season = ""
    if 3 <= current_month <= 5:
        season = "spring"
    elif 6 <= current_month <= 8:
        season = "summer"
    elif 9 <= current_month <= 11:
        season = "fall"
    else:
        season = "winter"

    for plant in plants:
        plant_name = plant.get('name', 'Unknown')

        if season == "winter":
            detailed_analytics['seasonal_care_adjustments'][plant_name] = {
                "watering": "Reduce watering frequency by approximately 25-30%",
                "light": "Consider supplemental grow lights due to shorter daylight hours",
                "fertilizer": "Reduce or pause fertilizing until spring",
                "humidity": "Monitor humidity levels as indoor heating can dry the air"
            }
        elif season == "summer":
            detailed_analytics['seasonal_care_adjustments'][plant_name] = {
                "watering": "Check soil moisture more frequently as plants may dry out faster",
                "light": "Protect from intense direct sunlight that may scorch leaves",
                "fertilizer": "This is the active growth period - maintain regular fertilizing schedule",
                "humidity": "Consider misting or using a humidifier in air-conditioned environments"
            }
        else:
            detailed_analytics['seasonal_care_adjustments'][plant_name] = {
                "watering": "Adjust watering based on growth activity and temperature",
                "light": "Monitor changing light patterns as seasons shift",
                "fertilizer": "Apply fertilizer according to regular schedule",
                "humidity": "Maintain humidity appropriate for plant needs"
            }

    return {
        'available': True,
        'basic': basic_analytics,
        'detailed': detailed_analytics,
        'upgrade_message': None
    }


# -------------------------------------------------------------------------------
# Custom kit management
# -------------------------------------------------------------------------------

class KitManager:
    """Manager for custom kit creation and storage"""

    @staticmethod
    def save_custom_kit(
            user_email: str,
            kit_data: Dict[str, Any],
            tier: SubscriptionTier
    ) -> Dict[str, Any]:
        """
        Save a custom kit configuration for a user (subscribers only).

        Args:
            user_email: User's email address
            kit_data: Kit configuration data
            tier: User's subscription tier

        Returns:
            Response with status and message
        """
        # Check if user can access this feature
        if not SubscriptionService.can_access_feature('can_save_custom_kits', tier):
            return {
                'success': False,
                'message': "Saving custom kits is a subscriber-only feature. Please upgrade your account."
            }

        try:
            # Generate a unique kit ID if not provided
            if 'kit_id' not in kit_data:
                kit_data['kit_id'] = f"custom_{uuid.uuid4().hex[:8]}"

            # Add metadata
            kit_data['created_at'] = datetime.now().isoformat()
            kit_data['last_modified'] = datetime.now().isoformat()
            kit_data['is_custom'] = True

            # Validate required fields
            required_fields = ['name', 'plant_ids']
            missing_fields = [field for field in required_fields if field not in kit_data]

            if missing_fields:
                return {
                    'success': False,
                    'message': f"Missing required fields: {', '.join(missing_fields)}"
                }

            # Save the kit
            result = update_user_kit(user_email, kit_data['kit_id'], kit_data)

            if result:
                return {
                    'success': True,
                    'message': "Custom kit saved successfully",
                    'kit_id': kit_data['kit_id']
                }
            else:
                return {
                    'success': False,
                    'message': "Failed to save custom kit. Please try again."
                }

        except Exception as e:
            logger.error(f"Error saving custom kit: {str(e)}")
            return {
                'success': False,
                'message': f"An error occurred: {str(e)}"
            }

    @staticmethod
    def get_user_custom_kits(user_email: str) -> List[KitDict]:
        """
        Retrieve all custom kits for a user.

        Args:
            user_email: User's email address

        Returns:
            List of custom kit dictionaries
        """
        try:
            user = get_user_by_email(user_email)
            if not user:
                logger.warning(f"User not found: {user_email}")
                return []

            custom_configurations = user.get('custom_configurations', {})
            if not isinstance(custom_configurations, dict):
                try:
                    if isinstance(custom_configurations, str):
                        custom_configurations = json.loads(custom_configurations)
                    else:
                        custom_configurations = {}
                except json.JSONDecodeError:
                    custom_configurations = {}

            custom_kits = []
            for kit_id, kit_data in custom_configurations.items():
                if isinstance(kit_data, dict) and kit_data.get('is_custom', False):
                    kit_copy = kit_data.copy()
                    kit_copy['id'] = kit_id
                    custom_kits.append(cast(KitDict, kit_copy))

            return custom_kits

        except Exception as e:
            logger.error(f"Error retrieving custom kits: {str(e)}")
            return []


# -------------------------------------------------------------------------------
# Caching and recommendation system
# -------------------------------------------------------------------------------

def cached_recommendation(timeout_seconds=300):
    """
    Cache recommendation results to improve API performance.

    Args:
        timeout_seconds: Cache timeout in seconds

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Skip caching if explicitly requested
            if kwargs.get('skip_cache', False):
                return func(*args, **kwargs)

            # Skip caching for subscribers unless explicitly enabled
            user_preferences = kwargs.get('user_preferences', {})
            tier = SubscriptionTier(user_preferences.get('subscription_tier', SubscriptionTier.FREE))
            if tier != SubscriptionTier.FREE and not kwargs.get('enable_subscriber_cache', False):
                return func(*args, **kwargs)

            # Create a cache key from the arguments
            # Don't include all user preferences, just the filtering ones
            filter_keys = ['location', 'experience_level', 'maintenance', 'light',
                           'humidity', 'temperature', 'size_constraint', 'functions']
            cache_dict = {k: user_preferences.get(k) for k in filter_keys if k in user_preferences}

            # Create a consistent cache key
            cache_key = json.dumps(cache_dict, sort_keys=True)

            # Check if we have a valid cached result
            if cache_key in _cache:
                result, timestamp = _cache[cache_key]
                age = datetime.now() - timestamp
                if age.total_seconds() < timeout_seconds:
                    logger.debug(f"Using cached recommendation result ({age.total_seconds():.1f}s old)")
                    return result

            # Call the original function
            result = func(*args, **kwargs)

            # Cache the result with current timestamp
            _cache[cache_key] = (result, datetime.now())

            return result

        return wrapper

    return decorator


@cached_recommendation(timeout_seconds=300)
def get_recommendations(
        user_preferences: UserPreferencesDict,
        plants_data: Optional[List[PlantDict]] = None,
        products_data: Optional[List[ProductDict]] = None,
        kits_data: Optional[List[KitDict]] = None,
        plant_product_data: Optional[List[Dict[str, Any]]] = None,
        user_email: Optional[str] = None,
        skip_cache: bool = False,
        enable_subscriber_cache: bool = False
) -> RecommendationResponseDict:
    """
    Get comprehensive plant and product recommendations based on user preferences.

    Args:
        user_preferences: User preference parameters
        plants_data: Optional list of plant dictionaries
        products_data: Optional list of product dictionaries
        kits_data: Optional list of kit dictionaries
        plant_product_data: Optional list of plant-product relationships
        user_email: User's email (for quota checking)
        skip_cache: Whether to skip caching
        enable_subscriber_cache: Whether to enable caching for subscribers

    Returns:
        Dictionary with recommendations and analysis

    Raises:
        InvalidPreferenceError: If user preferences are invalid
        DataRetrievalError: If data retrieval fails
        QuotaExceededError: If user has exceeded quota
    """
    logger.info(f"Processing recommendation request. User email: {user_email if user_email else 'Anonymous'}")

    try:
        # Validate user preferences
        if not user_preferences:
            raise InvalidPreferenceError("User preferences cannot be empty")

        # Validate required parameters
        required_params = ['location']
        for param in required_params:
            if param not in user_preferences or not user_preferences[param]:
                raise InvalidPreferenceError(f"Missing required parameter: {param}")

        # Validate parameter types
        if 'light_wattage' in user_preferences and user_preferences['light_wattage']:
            try:
                user_preferences['light_wattage'] = float(user_preferences['light_wattage'])
            except (ValueError, TypeError):
                raise InvalidPreferenceError(
                    f"Invalid light_wattage value: {user_preferences['light_wattage']}. Must be a number.")

        if 'temperature' in user_preferences and user_preferences['temperature']:
            try:
                user_preferences['temperature'] = float(user_preferences['temperature'])
            except (ValueError, TypeError):
                raise InvalidPreferenceError(
                    f"Invalid temperature value: {user_preferences['temperature']}. Must be a number.")

        if 'humidity' in user_preferences and user_preferences['humidity']:
            try:
                user_preferences['humidity'] = float(user_preferences['humidity'])
            except (ValueError, TypeError):
                raise InvalidPreferenceError(
                    f"Invalid humidity value: {user_preferences['humidity']}. Must be a number.")

        # Parse subscription tier from preferences
        tier_str = user_preferences.get('subscription_tier', SubscriptionTier.FREE.value)
        try:
            tier = SubscriptionTier(tier_str)
        except ValueError:
            logger.warning(f"Invalid subscription tier: {tier_str}. Defaulting to FREE.")
            tier = SubscriptionTier.FREE

        # Check quota if email provided (for API use)
        if user_email:
            has_quota, quota_message = SubscriptionService.check_quota(user_email, tier)
            if not has_quota:
                logger.warning(f"User {user_email} has exceeded their quota: {quota_message}")
                return cast(RecommendationResponseDict, {
                    'error': 'quota_exceeded',
                    'message': quota_message,
                    'subscription_tier': tier.value,
                    'retry_after': '24h'  # Added retry information
                })

        # Fetch data if not provided
        if plants_data is None or products_data is None or kits_data is None:
            logger.info("Fetching data from Google Sheets")
            try:
                plants_data, products_data, kits_data = get_data_from_sheets()
            except GoogleSheetsDataError as e:
                logger.error(f"Failed to retrieve data from Google Sheets: {str(e)}")
                raise DataRetrievalError(f"Failed to access plant database: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error retrieving data: {str(e)}", exc_info=True)
                raise DataRetrievalError(f"Unexpected error: {str(e)}")

        # Load plant-product relationships if not provided
        if plant_product_data is None:
            try:
                plant_product_data = get_plant_products_data()
            except Exception as e:
                logger.warning(f"Failed to get plant-product relationships: {str(e)}")
                plant_product_data = []
                logger.info("Continuing with empty plant-product relationships")

        # Filter premium plants for non-subscribers
        if tier == SubscriptionTier.FREE and plants_data:
            original_count = len(plants_data)
            plants_data = [plant for plant in plants_data if not plant.get('is_premium_content', False)]
            filtered_count = original_count - len(plants_data)
            if filtered_count > 0:
                logger.info(f"Filtered {filtered_count} premium plants for free tier user")

        # Create filter dictionary from user preferences
        filter_criteria = {}
        for key, pref_key in [
            ('location', 'location'),
            ('experience_level', 'experience_level'),
            ('maintenance', 'maintenance'),
            ('functions', 'functions'),
            ('light', 'light'),
            ('light_wattage', 'light_wattage'),
            ('temperature', 'temperature'),
            ('humidity', 'humidity')
        ]:
            if pref_key in user_preferences and user_preferences[pref_key]:
                filter_criteria[key] = user_preferences[pref_key]

        # Filter plants based on all criteria
        if not plants_data:
            logger.warning("No plant data available for filtering")
            filtered_plants = []
        else:
            filtered_plants = filter_plants(plants_data, filter_criteria)
            logger.info(f"Filtered plants from {len(plants_data)} to {len(filtered_plants)}")

            if not filtered_plants:
                logger.warning("No plants match the filter criteria")
                # Return informative response with suggestions
                return cast(RecommendationResponseDict, {
                    'error': 'no_matches',
                    'message': "No plants match your criteria. Try broadening your preferences.",
                    'suggestions': get_filter_suggestions(plants_data, filter_criteria),
                    'subscription_tier': tier.value
                })

        # Rank plants by preference matching
        ranked_plants = rank_plants(filtered_plants, user_preferences)
        logger.info(f"Ranked {len(ranked_plants)} plants by preference match")

        # Match with suitable products using the junction table
        recommended_products = match_products_to_plants(ranked_plants, products_data, plant_product_data)
        logger.info(f"Found {len(recommended_products)} matching products")

        # Find suitable pre-defined kits
        recommended_kits = find_matching_kits(
            user_preferences.get('location', ''),
            kits_data,
            user_preferences
        )
        logger.info(f"Found {len(recommended_kits)} matching kits")

        # Apply pricing adjustments based on subscription tier
        adjusted_products = [calculate_pricing(product, tier) for product in recommended_products]
        adjusted_kits = [calculate_pricing(kit, tier) for kit in recommended_kits]

        # Create care schedule for recommended plants
        care_schedule = create_care_schedule(ranked_plants)

        # Limit number of recommendations based on tier and preferences
        max_plants = int(user_preferences.get('max_plants', 10))
        max_products = int(user_preferences.get('max_products', 5))
        max_kits = int(user_preferences.get('max_kits', 3))

        # Premium subscribers get all results
        if tier == SubscriptionTier.PREMIUM:
            max_plants = len(ranked_plants)
            max_products = len(adjusted_products)
            max_kits = len(adjusted_kits)

        # Create light analysis if wattage provided
        light_analysis = []
        if 'light_wattage' in user_preferences and user_preferences['light_wattage']:
            wattage = user_preferences['light_wattage']
            for plant in ranked_plants[:max_plants]:
                light_analysis.append(analyze_light_requirements(plant, wattage))

        # Get summary statistics
        stats = {
            'total_plants_matching': len(ranked_plants),
            'total_products_matching': len(adjusted_products),
            'total_kits_matching': len(adjusted_kits),
            'filters_applied': list(filter_criteria.keys()),
            'location': user_preferences.get('location', 'Not specified'),
            'experience_level': user_preferences.get('experience_level', 'Not specified'),
            'timestamp': datetime.now().isoformat(),
            'request_id': str(uuid.uuid4())
        }

        # Generate detailed analytics based on subscription tier
        analytics = generate_detailed_analytics(ranked_plants, user_preferences, tier)

        # Add custom kits for subscribers with emails
        custom_kits = []
        if user_email and tier != SubscriptionTier.FREE:
            try:
                custom_kits = KitManager.get_user_custom_kits(user_email)
                # Add custom kits to recommendations if they match the location
                if custom_kits and 'location' in user_preferences:
                    location = user_preferences['location'].lower()
                    for kit in custom_kits:
                        kit_locations = kit.get('locations', [])
                        if isinstance(kit_locations, str):
                            kit_locations = [loc.strip() for loc in kit_locations.split(',')]
                        kit_locations = [loc.lower() for loc in kit_locations]

                        if location in kit_locations:
                            kit['is_custom'] = True
                            adjusted_kits.append(kit)
            except Exception as e:
                logger.warning(f"Error fetching custom kits for {user_email}: {str(e)}")
                # Continue without custom kits rather than failing

        # Add subscription information to response
        result: RecommendationResponseDict = {
            'plants': ranked_plants[:max_plants],
            'products': adjusted_products[:max_products],
            'kits': adjusted_kits[:max_kits],
            'care_schedule': care_schedule,
            'light_analysis': light_analysis,
            'analytics': analytics,
            'stats': stats,
            'subscription_tier': tier.value,
            'subscriber_features': {
                'can_save_custom_kits': SubscriptionService.can_access_feature('can_save_custom_kits', tier),
                'service_fee_percentage': SubscriptionService.SERVICE_FEES.get(tier, 0.10) * 100,
                'detailed_analytics': SubscriptionService.can_access_feature('detailed_analytics', tier),
                'unlimited_plants': SubscriptionService.can_access_feature('unlimited_plants', tier),
                'priority_support': SubscriptionService.can_access_feature('priority_support', tier),
            },
            'custom_kit': None,
            'error': None,
            'message': None,
            'version': '1.0'
        }

        # Add kit saving information for subscribers
        if SubscriptionService.can_access_feature('can_save_custom_kits', tier):
            result['custom_kit'] = {
                'can_save': True,
                'save_endpoint': '/api/kits/save',
                'custom_kits_count': len(custom_kits)
            }

        logger.info(
            f"Successfully generated recommendations. Plants: {len(result['plants'])}, Products: {len(result['products'])}, Kits: {len(result['kits'])}")
        return result

    except InvalidPreferenceError as e:
        logger.warning(f"Invalid preference: {str(e)}")
        return cast(RecommendationResponseDict, {
            'error': 'invalid_preference',
            'message': str(e),
            'subscription_tier': tier.value if 'tier' in locals() else SubscriptionTier.FREE.value,
            'version': '1.0'
        })
    except DataRetrievalError as e:
        logger.error(f"Data retrieval error: {str(e)}")
        return cast(RecommendationResponseDict, {
            'error': 'data_error',
            'message': f"Error retrieving data: {str(e)}",
            'subscription_tier': tier.value if 'tier' in locals() else SubscriptionTier.FREE.value,
            'version': '1.0'
        })
    except QuotaExceededError as e:
        logger.warning(f"Quota exceeded: {str(e)}")
        return cast(RecommendationResponseDict, {
            'error': 'quota_exceeded',
            'message': str(e),
            'subscription_tier': tier.value if 'tier' in locals() else SubscriptionTier.FREE.value,
            'version': '1.0'
        })
    except Exception as e:
        logger.error(f"Unexpected error in get_recommendations: {str(e)}", exc_info=True)
        return cast(RecommendationResponseDict, {
            'error': 'unknown_error',
            'message': f"An unexpected error occurred: {str(e)}",
            'subscription_tier': tier.value if 'tier' in locals() else SubscriptionTier.FREE.value,
            'version': '1.0'
        })


def get_filter_suggestions(plants_data: List[PlantDict], filter_criteria: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Generate suggestions for adjusting filter criteria when no plants match.

    Args:
        plants_data: Complete plant data
        filter_criteria: Current filter criteria that resulted in no matches

    Returns:
        Dictionary with suggestions for each filter criteria
    """
    suggestions = {}

    # Suggest alternative locations if location filter is too restrictive
    if 'location' in filter_criteria:
        current_location = filter_criteria['location']
        alternative_locations = set()

        for plant in plants_data:
            compatible_locations = plant.get('compatible_locations', [])
            if isinstance(compatible_locations, str):
                compatible_locations = [loc.strip() for loc in compatible_locations.split(',')]

            for loc in compatible_locations:
                if loc and loc != current_location:
                    alternative_locations.add(loc)

        if alternative_locations:
            suggestions['location'] = list(alternative_locations)[:5]  # Limit to 5 suggestions

    # Suggest alternative light conditions if light filter is too restrictive
    if 'light' in filter_criteria:
        current_light = filter_criteria['light']
        light_levels = ['low', 'medium', 'bright_indirect', 'direct']

        if current_light in light_levels:
            # Suggest adjacent light levels
            idx = light_levels.index(current_light)
            alternative_lights = []

            if idx > 0:
                alternative_lights.append(light_levels[idx - 1])
            if idx < len(light_levels) - 1:
                alternative_lights.append(light_levels[idx + 1])

            suggestions['light'] = alternative_lights

    # Suggest alternative experience levels
    if 'experience_level' in filter_criteria:
        current_level = filter_criteria['experience_level']
        if current_level == 'beginner':
            suggestions['experience_level'] = ['intermediate']
        elif current_level == 'advanced':
            suggestions['experience_level'] = ['intermediate']

    # Suggest alternative maintenance preferences
    if 'maintenance' in filter_criteria:
        current_maintenance = filter_criteria['maintenance']
        if current_maintenance == 'low':
            suggestions['maintenance'] = ['medium']
        elif current_maintenance == 'high':
            suggestions['maintenance'] = ['medium']

    return suggestions


# Add this to recommendation_engine.py or create a new chat_processor.py file

import re
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

# Use the existing filter functions
from core.filters import (
    filter_by_location, filter_by_difficulty, filter_by_maintenance,
    filter_by_light_requirements, filter_plants
)

# In-memory conversation state
_conversations = {}


def process_chat_message(message: str, session_id: str) -> Dict[str, Any]:
    """
    Process a chat message and generate a response with plant recommendations.

    Args:
        message: User's message
        session_id: Unique session identifier

    Returns:
        Response dictionary with message content and potential recommendations
    """
    # Get or initialize conversation state
    if session_id not in _conversations:
        _conversations[session_id] = {
            'state': 'greeting',
            'preferences': {},
            'last_update': datetime.now().isoformat()
        }

    conversation = _conversations[session_id]

    # Convert message to lowercase for easier matching
    message_lower = message.lower()

    # Check for greetings
    greetings = ['hi', 'hello', 'hey', 'start', 'help']
    if any(greeting in message_lower for greeting in greetings) and conversation['state'] == 'greeting':
        conversation['state'] = 'ask_location'
        return {
            'type': 'text',
            'content': "Hi! I'm your GrowVRD plant assistant. I can help you find the perfect plants for your space. Where would you like to add plants? (living room, bedroom, bathroom, kitchen, office, balcony)"
        }

    # Handle location input
    if conversation['state'] == 'ask_location' or 'room' in message_lower or 'space' in message_lower:
        locations = {
            'living room': 'living_room',
            'bedroom': 'bedroom',
            'bathroom': 'bathroom',
            'kitchen': 'kitchen',
            'office': 'office',
            'balcony': 'balcony'
        }

        matched_location = None
        for location, code in locations.items():
            if location in message_lower:
                matched_location = code
                break

        if matched_location:
            conversation['preferences']['location'] = matched_location
            conversation['state'] = 'ask_light'

            return {
                'type': 'text',
                'content': f"Great! Now, how much light does your {matched_location.replace('_', ' ')} get? (low, medium, bright indirect, or direct sunlight)"
            }
        elif conversation['state'] == 'ask_location':
            return {
                'type': 'text',
                'content': "I didn't catch that. Please specify where you want to add plants: living room, bedroom, bathroom, kitchen, office, or balcony?"
            }

    # Handle light input
    if conversation['state'] == 'ask_light' or any(
            light in message_lower for light in ['light', 'sunlight', 'sun', 'bright', 'dark']):
        light_levels = {
            'low': 'low',
            'dark': 'low',
            'medium': 'medium',
            'moderate': 'medium',
            'bright indirect': 'bright_indirect',
            'indirect': 'bright_indirect',
            'direct': 'direct',
            'full sun': 'direct'
        }

        matched_light = None
        for light, code in light_levels.items():
            if light in message_lower:
                matched_light = code
                break

        if matched_light:
            conversation['preferences']['light'] = matched_light
            conversation['state'] = 'ask_experience'

            return {
                'type': 'text',
                'content': "How would you describe your experience with plants? (beginner, intermediate, advanced)"
            }
        elif conversation['state'] == 'ask_light':
            return {
                'type': 'text',
                'content': "I need to know about the lighting conditions. Is it low light, medium light, bright indirect light, or direct sunlight?"
            }

    # Handle experience input
    if conversation['state'] == 'ask_experience' or any(
            exp in message_lower for exp in ['beginner', 'intermediate', 'advanced', 'expert', 'new', 'experienced']):
        experience_levels = {
            'beginner': 'beginner',
            'new': 'beginner',
            'intermediate': 'intermediate',
            'advanced': 'advanced',
            'expert': 'advanced'
        }

        matched_experience = None
        for exp, code in experience_levels.items():
            if exp in message_lower:
                matched_experience = code
                break

        if matched_experience:
            conversation['preferences']['experience_level'] = matched_experience
            conversation['state'] = 'ask_maintenance'

            return {
                'type': 'text',
                'content': "How much time do you want to spend on plant maintenance? (low, medium, high)"
            }
        elif conversation['state'] == 'ask_experience':
            return {
                'type': 'text',
                'content': "Please let me know your experience level with plants: beginner, intermediate, or advanced?"
            }

    # Handle maintenance input
    if conversation['state'] == 'ask_maintenance' or any(
            maint in message_lower for maint in ['maintenance', 'care', 'time', 'effort']):
        maintenance_levels = {
            'low': 'low',
            'minimal': 'low',
            'medium': 'medium',
            'moderate': 'medium',
            'high': 'high'
        }

        matched_maintenance = None
        for maint, code in maintenance_levels.items():
            if maint in message_lower:
                matched_maintenance = code
                break

        if matched_maintenance:
            conversation['preferences']['maintenance'] = matched_maintenance
            conversation['state'] = 'recommend'

            # Now we have enough information to make recommendations
            return generate_recommendations(conversation['preferences'])
        elif conversation['state'] == 'ask_maintenance':
            return {
                'type': 'text',
                'content': "How much maintenance are you willing to do? Low (water every 2-4 weeks), medium (weekly attention), or high (frequent care)?"
            }

    # Handle recommendation requests
    if 'recommend' in message_lower or 'suggestion' in message_lower or 'plants' in message_lower:
        if len(conversation['preferences']) >= 2:  # At least location and one other preference
            conversation['state'] = 'recommend'
            return generate_recommendations(conversation['preferences'])
        else:
            missing = []
            if 'location' not in conversation['preferences']:
                missing.append('location')
            if 'light' not in conversation['preferences']:
                missing.append('light conditions')

            return {
                'type': 'text',
                'content': f"I need a bit more information before I can make good recommendations. Could you tell me about your {', '.join(missing)}?"
            }

    # Handle reset/restart
    if 'restart' in message_lower or 'reset' in message_lower or 'start over' in message_lower:
        _conversations[session_id] = {
            'state': 'greeting',
            'preferences': {},
            'last_update': datetime.now().isoformat()
        }

        return {
            'type': 'text',
            'content': "Let's start over! Where would you like to add plants? (living room, bedroom, bathroom, kitchen, office, balcony)"
        }

    # Default response for unclear input
    return {
        'type': 'text',
        'content': "I'm not sure what you're asking. You can ask for plant recommendations, or tell me about your space, lighting conditions, experience level, or maintenance preferences."
    }


def generate_recommendations(preferences: Dict[str, str]) -> Dict[str, Any]:
    """
    Generate plant recommendations based on user preferences.

    Args:
        preferences: Dictionary of user preferences

    Returns:
        Recommendation response
    """
    # In a real implementation, this would call the recommendation engine
    try:
        from core.mock_data import get_mock_plants
        plants_data = get_mock_plants()

        # Apply filters based on preferences
        filtered_plants = filter_plants(plants_data, preferences)

        # Limit to top 3 plants for chat interface
        top_plants = filtered_plants[:3]

        if not top_plants:
            return {
                'type': 'text',
                'content': "I couldn't find plants that match all your criteria. Try broadening your preferences a bit."
            }

        # Create a response with recommendations
        plants_text = "\n\n".join([
            f"**{plant.get('name', '').replace('_', ' ').title()}** ({plant.get('scientific_name', '').replace('_', ' ')}): {plant.get('description', 'No description available.')}"
            for plant in top_plants
        ])

        location = preferences.get('location', 'your space').replace('_', ' ')

        return {
            'type': 'recommendation',
            'content': f"Based on your preferences, here are some plants that would work well in {location}:",
            'data': {
                'plants': top_plants,
                'preferences': preferences
            }
        }
    except Exception as e:
        return {
            'type': 'text',
            'content': f"I encountered an error generating recommendations. Please try again later."
        }