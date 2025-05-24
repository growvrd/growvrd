import logging
from typing import List, Dict, Any, Optional, Union, Callable

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('filters')


def safe_filter(filter_func: Callable) -> Callable:
    """
    Decorator to handle common error cases in filter functions.

    Args:
        filter_func: The filter function to wrap

    Returns:
        Wrapped function with error handling
    """

    def wrapper(plants_data: List[Dict[str, Any]], *args, **kwargs) -> List[Dict[str, Any]]:
        # Check if plants_data is valid
        if not plants_data:
            logger.warning(f"Empty plants data provided to {filter_func.__name__}")
            return []

        if not isinstance(plants_data, list):
            logger.error(f"Invalid plants data type in {filter_func.__name__}: {type(plants_data)}")
            return []

        # Proceed with the actual filter function
        try:
            return filter_func(plants_data, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {filter_func.__name__}: {str(e)}")
            return plants_data  # Return original data on error

    return wrapper


@safe_filter
def filter_by_location(
        plants_data: List[Dict[str, Any]],
        location: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter plants based on compatibility with a specific location.

    Args:
        plants_data: List of plant dictionaries
        location: Room location (e.g., 'bathroom', 'living_room')

    Returns:
        Filtered plant list
    """
    if not location:
        return plants_data

    location = location.lower().strip()
    if not location:
        return plants_data

    filtered_plants = []

    for plant in plants_data:
        # Get the compatible locations for this plant
        compatible_locations = plant.get('compatible_locations', [])

        # Handle different data formats for compatible_locations
        if isinstance(compatible_locations, str):
            compatible_locations = [loc.strip() for loc in compatible_locations.split(',')]

        # Convert all locations to lowercase for case-insensitive comparison
        compatible_locations = [loc.lower() for loc in compatible_locations if loc]

        # Add plant if the location matches
        if location in compatible_locations:
            filtered_plants.append(plant)

    logger.debug(f"Location filter '{location}' reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_difficulty(
        plants_data: List[Dict[str, Any]],
        user_experience_level: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on difficulty level matching user experience.

    Args:
        plants_data: List of plant dictionaries
        user_experience_level: 'beginner', 'intermediate', or 'advanced'

    Returns:
        Filtered plant list
    """
    if not user_experience_level:
        return plants_data

    user_experience_level = user_experience_level.lower().strip()

    # Define difficulty thresholds for each experience level
    difficulty_thresholds = {
        'beginner': 3,  # Difficulty 1-3
        'intermediate': 6,  # Difficulty 1-6
        'advanced': 10  # Difficulty 1-10 (all plants)
    }

    # Get maximum difficulty level for the given experience level
    max_difficulty = difficulty_thresholds.get(user_experience_level, 3)  # Default to beginner

    # Filter plants based on numeric difficulty
    filtered_plants = []
    for plant in plants_data:
        try:
            difficulty = int(plant.get('difficulty', 10))  # Default to highest difficulty
            if difficulty <= max_difficulty:
                filtered_plants.append(plant)
        except (ValueError, TypeError):
            # If difficulty is not a number, try to interpret string values
            difficulty_str = str(plant.get('difficulty', '')).lower()
            if 'beginner' in difficulty_str or 'easy' in difficulty_str:
                filtered_plants.append(plant)
            elif user_experience_level != 'beginner' and (
                    'intermediate' in difficulty_str or 'moderate' in difficulty_str):
                filtered_plants.append(plant)
            elif user_experience_level == 'advanced' and (
                    'advanced' in difficulty_str or 'difficult' in difficulty_str):
                filtered_plants.append(plant)

    logger.debug(
        f"Difficulty filter '{user_experience_level}' reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_maintenance(
        plants_data: List[Dict[str, Any]],
        upkeep_preference: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on maintenance requirements.

    Args:
        plants_data: List of plant dictionaries
        upkeep_preference: 'low', 'medium', or 'high'

    Returns:
        Filtered plant list
    """
    if not upkeep_preference:
        return plants_data

    upkeep_preference = upkeep_preference.lower().strip()

    # Define maintenance level mapping
    maintenance_levels = {
        'low': ['low'],
        'medium': ['low', 'medium', 'moderate'],
        'high': ['low', 'medium', 'moderate', 'high']
    }

    # Get allowed maintenance levels
    allowed_levels = maintenance_levels.get(upkeep_preference, ['low'])

    # Filter plants based on maintenance level
    filtered_plants = []
    for plant in plants_data:
        maintenance = str(plant.get('maintenance', '')).lower()
        if any(level in maintenance for level in allowed_levels):
            filtered_plants.append(plant)

    logger.debug(
        f"Maintenance filter '{upkeep_preference}' reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_function(
        plants_data: List[Dict[str, Any]],
        desired_functions: Optional[List[str]]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on their functionality.

    Args:
        plants_data: List of plant dictionaries
        desired_functions: List of desired functions (e.g., ['air_purification', 'decoration'])

    Returns:
        Filtered plant list
    """
    if not desired_functions:
        return plants_data

    # Convert desired functions to lowercase for case-insensitive comparison
    desired_functions_lower = [func.lower().strip() for func in desired_functions if func]

    if not desired_functions_lower:
        return plants_data

    # Filter plants that have at least one of the desired functions
    filtered_plants = []
    for plant in plants_data:
        # Get plant functions and handle different formats
        plant_functions = plant.get('functions', [])

        if isinstance(plant_functions, str):
            plant_functions = [func.strip() for func in plant_functions.split(',')]

        # Convert to lowercase for comparison
        plant_functions_lower = [func.lower() for func in plant_functions if func]

        # Check if any desired function matches any plant function
        if any(desired_func in plant_functions_lower for desired_func in desired_functions_lower):
            filtered_plants.append(plant)

    logger.debug(f"Function filter reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_light_requirements(
        plants_data: List[Dict[str, Any]],
        available_light: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on available light conditions.

    Args:
        plants_data: List of plant dictionaries
        available_light: User's available light ('low', 'medium', 'bright_indirect', 'direct')

    Returns:
        Plants that can thrive with the available light
    """
    if not available_light:
        return plants_data

    available_light = available_light.lower().strip()

    # Define light level hierarchy
    light_levels = {
        'low': ['low'],
        'medium': ['low', 'medium'],
        'bright_indirect': ['low', 'medium', 'bright_indirect'],
        'direct': ['low', 'medium', 'bright_indirect', 'direct']
    }

    # Get compatible light levels
    compatible_levels = light_levels.get(available_light, ['low'])

    filtered_plants = []
    for plant in plants_data:
        # Check both LED and natural light requirements
        led_light_req = plant.get('led_light_requirements', '').lower()
        natural_light_req = plant.get('natural_sunlight_needs', '').lower()

        # Plant can work if either LED or natural light requirements match
        if any(level in led_light_req for level in compatible_levels) or \
                any(level in natural_light_req for level in compatible_levels):
            filtered_plants.append(plant)

    logger.debug(f"Light filter '{available_light}' reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_light_wattage(
        plants_data: List[Dict[str, Any]],
        available_wattage: Optional[Union[int, float]]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on available light wattage.

    Args:
        plants_data: List of plant dictionaries
        available_wattage: User's available light wattage

    Returns:
        Plants that can thrive with the available light
    """
    if available_wattage is None:
        return plants_data

    try:
        available_wattage = float(available_wattage)
    except (ValueError, TypeError):
        logger.warning(f"Invalid light wattage value: {available_wattage}")
        return plants_data

    filtered_plants = []
    for plant in plants_data:
        try:
            min_wattage = float(plant.get('led_wattage_min', 0))

            # If available wattage meets minimum requirements
            if min_wattage <= available_wattage:
                filtered_plants.append(plant)
            # Allow for some flexibility (plants can adapt to slightly lower light)
            elif min_wattage > 0 and min_wattage * 0.9 <= available_wattage:  # 10% tolerance
                filtered_plants.append(plant)
        except (ValueError, TypeError):
            # If wattage data is corrupt, err on the side of inclusion
            logger.warning(f"Invalid led_wattage_min for plant: {plant.get('name')}")
            filtered_plants.append(plant)

    logger.debug(
        f"Light wattage filter ({available_wattage}W) reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_temperature(
        plants_data: List[Dict[str, Any]],
        temperature: Optional[Union[int, float]]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on available temperature.

    Args:
        plants_data: List of plant dictionaries
        temperature: User's available temperature in °F

    Returns:
        Plants that can thrive at the given temperature
    """
    if temperature is None:
        return plants_data

    try:
        temperature = float(temperature)
    except (ValueError, TypeError):
        logger.warning(f"Invalid temperature value: {temperature}")
        return plants_data

    filtered_plants = []
    for plant in plants_data:
        try:
            temp_min = float(plant.get('temperature_min', 32))  # Default to freezing
            temp_max = float(plant.get('temperature_max', 100))  # Default to very hot

            # Check if temperature is within the plant's range
            if temp_min <= temperature <= temp_max:
                filtered_plants.append(plant)
        except (ValueError, TypeError):
            # If temperature data is corrupt, err on the side of inclusion
            logger.warning(f"Invalid temperature range for plant: {plant.get('name')}")
            filtered_plants.append(plant)

    logger.debug(
        f"Temperature filter ({temperature}°F) reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_humidity(
        plants_data: List[Dict[str, Any]],
        humidity: Optional[Union[int, float]]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on available humidity.

    Args:
        plants_data: List of plant dictionaries
        humidity: User's available humidity percentage (0-100)

    Returns:
        Plants that can thrive at the given humidity
    """
    if humidity is None:
        return plants_data

    try:
        humidity = float(humidity)
        # Ensure humidity is within valid range
        humidity = max(0, min(100, humidity))
    except (ValueError, TypeError):
        logger.warning(f"Invalid humidity value: {humidity}")
        return plants_data

    # Map percentage to categories
    humidity_category = 'low'
    if humidity >= 70:
        humidity_category = 'high'
    elif humidity >= 40:
        humidity_category = 'medium'

    filtered_plants = []
    for plant in plants_data:
        plant_humidity = plant.get('humidity_preference', '').lower()

        # Low humidity plants work in low humidity
        if humidity_category == 'low' and 'low' in plant_humidity:
            filtered_plants.append(plant)
        # Medium humidity plants work in medium or high humidity
        elif humidity_category == 'medium' and any(level in plant_humidity for level in ['low', 'medium']):
            filtered_plants.append(plant)
        # High humidity plants work in any humidity level
        elif humidity_category == 'high':
            filtered_plants.append(plant)
        # Default case: if no humidity preference is specified, include the plant
        elif not plant_humidity:
            filtered_plants.append(plant)

    logger.debug(f"Humidity filter ({humidity}%) reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


@safe_filter
def filter_by_search_term(
        plants_data: List[Dict[str, Any]],
        search_term: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Filter plants based on a search term (for API search functionality).

    Args:
        plants_data: List of plant dictionaries
        search_term: Term to search for in plant name, description or searchable_text

    Returns:
        Plants matching the search term
    """
    if not search_term:
        return plants_data

    search_term = search_term.lower().strip()

    if not search_term:
        return plants_data

    filtered_plants = []
    for plant in plants_data:
        name = str(plant.get('name', '')).lower()
        scientific_name = str(plant.get('scientific_name', '')).lower()
        description = str(plant.get('description', '')).lower()
        searchable_text = str(plant.get('searchable_text', '')).lower()

        if (search_term in name or
                search_term in scientific_name or
                search_term in description or
                search_term in searchable_text):
            filtered_plants.append(plant)

    logger.debug(f"Search filter '{search_term}' reduced plants from {len(plants_data)} to {len(filtered_plants)}")
    return filtered_plants


def filter_plants_by_subscription(
        plants_data: List[Dict[str, Any]],
        subscription_status: str = "free"
) -> List[Dict[str, Any]]:
    """
    Filter plants based on subscription status - subscribers get access to premium plants.

    Args:
        plants_data: List of plant dictionaries
        subscription_status: User's subscription status ('free' or 'subscriber')

    Returns:
        Filtered plant list based on subscription access
    """
    if not plants_data:
        return []

    if subscription_status.lower() == "subscriber":
        # Subscribers get all plants
        return plants_data

    # Free users only get non-premium plants
    return [plant for plant in plants_data if not plant.get('is_premium_content', False)]


def filter_plants(
        plants_data: List[Dict[str, Any]],
        filters: Dict[str, Any] = None,
        subscription_status: str = "free"
) -> List[Dict[str, Any]]:
    """
    Apply multiple filters to plant data with subscription awareness.

    Args:
        plants_data: List of plant dictionaries
        filters: Dictionary containing filter criteria
            Possible keys:
                - location (str): Room location
                - experience_level (str): User experience level
                - maintenance (str): Maintenance preference
                - functions (list): Desired functions
                - light (str): Light conditions
                - light_wattage (float): Available light wattage
                - temperature (float): Room temperature
                - humidity (float): Room humidity percentage
                - search_term (str): Text to search for
        subscription_status: User's subscription status ('free' or 'subscriber')

    Returns:
        Filtered plant list
    """
    if not filters:
        # Even without specific filters, still filter by subscription status
        return filter_plants_by_subscription(plants_data, subscription_status)

    # First filter by subscription to respect access restrictions
    filtered_plants = filter_plants_by_subscription(plants_data, subscription_status)

    # Apply search filter first if present
    if 'search_term' in filters and filters['search_term']:
        filtered_plants = filter_by_search_term(filtered_plants, filters['search_term'])

    # Apply each specific filter in sequence if the filter value is provided
    if 'location' in filters and filters['location']:
        filtered_plants = filter_by_location(filtered_plants, filters['location'])

    if 'experience_level' in filters and filters['experience_level']:
        filtered_plants = filter_by_difficulty(filtered_plants, filters['experience_level'])

    if 'maintenance' in filters and filters['maintenance']:
        filtered_plants = filter_by_maintenance(filtered_plants, filters['maintenance'])

    if 'functions' in filters and filters['functions']:
        filtered_plants = filter_by_function(filtered_plants, filters['functions'])

    if 'light' in filters and filters['light']:
        filtered_plants = filter_by_light_requirements(filtered_plants, filters['light'])

    if 'light_wattage' in filters and filters['light_wattage']:
        filtered_plants = filter_by_light_wattage(filtered_plants, filters['light_wattage'])

    if 'temperature' in filters and filters['temperature']:
        filtered_plants = filter_by_temperature(filtered_plants, filters['temperature'])

    if 'humidity' in filters and filters['humidity']:
        filtered_plants = filter_by_humidity(filtered_plants, filters['humidity'])

    # Log filter results
    total_filters = sum(1 for f in filters.values() if f)
    logger.info(f"Applied {total_filters} filters, reduced plants from {len(plants_data)} to {len(filtered_plants)}")

    return filtered_plants


def paginate_results(
        filtered_plants: List[Dict[str, Any]],
        page: int = 1,
        page_size: int = 10
) -> Dict[str, Any]:
    """
    Paginate filtered results for API responses.

    Args:
        filtered_plants: List of filtered plant dictionaries
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Dictionary with pagination info and results
    """
    # Validate inputs
    page = max(1, page)  # Ensure page is at least 1
    page_size = max(1, min(100, page_size))  # Limit page_size between 1 and 100

    # Calculate pagination values
    total_items = len(filtered_plants)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = min(page, total_pages)

    # Calculate start and end indices
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)

    # Get the items for the current page
    page_items = filtered_plants[start_idx:end_idx]

    # Return pagination info along with page items
    return {
        "items": page_items,
        "pagination": {
            "page": current_page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": current_page < total_pages,
            "has_prev": current_page > 1
        }
    }


def rank_plants(
        filtered_plants: List[Dict[str, Any]],
        user_preferences: Dict[str, Any],
        subscription_status: str = "free"
) -> List[Dict[str, Any]]:
    """
    Rank filtered plants based on how well they match user preferences.

    Args:
        filtered_plants: List of filtered plant dictionaries
        user_preferences: User preferences for ranking
        subscription_status: User's subscription status

    Returns:
        Sorted plants from best to worst match
    """
    if not filtered_plants:
        return []

    if not user_preferences:
        return filtered_plants

    # Define preference weights
    weights = {
        'location': 3.0,
        'light': 2.5,
        'maintenance': 2.0,
        'experience_level': 1.5,
        'functions': 1.0,
        'temperature': 0.8,
        'humidity': 0.7
    }

    # Override with custom weights if provided
    if 'weights' in user_preferences:
        for key, value in user_preferences['weights'].items():
            weights[key] = float(value)

    # Score each plant
    for plant in filtered_plants:
        score = 0.0
        normalized_score = 0.0
        max_possible_score = 0.0
        score_components = {}

        # Location match
        if 'location' in user_preferences and user_preferences['location']:
            location_weight = weights.get('location', 3.0)
            max_possible_score += location_weight

            compatible_locations = plant.get('compatible_locations', [])
            if isinstance(compatible_locations, str):
                compatible_locations = [loc.strip() for loc in compatible_locations.split(',')]

            compatible_locations = [loc.lower() for loc in compatible_locations if loc]

            if user_preferences['location'].lower() in compatible_locations:
                score += location_weight
                score_components['location'] = location_weight

        # Light preference match
        if 'light' in user_preferences and user_preferences['light']:
            light_weight = weights.get('light', 2.5)
            max_possible_score += light_weight

            light_req = plant.get('led_light_requirements', '').lower()
            if user_preferences['light'].lower() in light_req:
                score += light_weight
                score_components['light'] = light_weight

        # Maintenance match
        if 'maintenance' in user_preferences and user_preferences['maintenance']:
            maintenance_weight = weights.get('maintenance', 2.0)
            max_possible_score += maintenance_weight

            maint_pref = user_preferences['maintenance'].lower()
            plant_maint = plant.get('maintenance', '')

            # Convert to numeric if needed
            if isinstance(plant_maint, str):
                maintenance_map = {
                    'very low': 1, 'low': 2, 'medium': 3,
                    'moderate': 3, 'high': 4, 'very high': 5
                }
                plant_maint_value = maintenance_map.get(plant_maint.lower(), 3)
            else:
                try:
                    plant_maint_value = int(plant_maint) if plant_maint is not None else 3
                except (ValueError, TypeError):
                    plant_maint_value = 3

            # Map preference to thresholds
            maint_thresholds = {'low': 2, 'medium': 4, 'high': 5}
            max_maint = maint_thresholds.get(maint_pref, 5)

            if plant_maint_value <= max_maint:
                # Scale the score based on how well it matches preference
                match_percentage = 1.0 - (plant_maint_value / max_maint)
                adjusted_score = maintenance_weight * match_percentage
                score += adjusted_score
                score_components['maintenance'] = adjusted_score

        # Function match
        if 'functions' in user_preferences and user_preferences['functions']:
            function_weight = weights.get('functions', 1.0)
            max_possible_score += function_weight

            desired_functions = [f.lower() for f in user_preferences['functions'] if f]
            plant_functions = plant.get('functions', [])

            if isinstance(plant_functions, str):
                plant_functions = [f.strip() for f in plant_functions.split(',')]

            plant_functions = [f.lower() for f in plant_functions if f]

            # Count the number of matching functions
            matches = sum(1 for df in desired_functions if any(df in pf for pf in plant_functions))

            if desired_functions and matches:
                match_percentage = matches / len(desired_functions)
                adjusted_score = function_weight * match_percentage
                score += adjusted_score
                score_components['functions'] = adjusted_score

        # Calculate normalized score if possible (0-100 scale)
        if max_possible_score > 0:
            normalized_score = (score / max_possible_score) * 100

        # Store scores with plant
        plant['match_score'] = score
        plant['normalized_score'] = round(normalized_score, 1)
        plant['score_components'] = score_components

        # Enhanced features for subscribers
        if subscription_status.lower() == "subscriber":
            # Add detailed score explanations for subscribers
            explanations = []
            for factor, score_value in score_components.items():
                explanations.append({
                    "factor": factor,
                    "score": score_value,
                    "max_possible": weights.get(factor, 1.0),
                    "percentage": round((score_value / weights.get(factor, 1.0)) * 100, 1)
                })

            plant['score_explanation'] = explanations

    # Sort by score (highest first)
    return sorted(filtered_plants, key=lambda p: p.get('match_score', 0), reverse=True)