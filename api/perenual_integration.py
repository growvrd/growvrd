"""
Perenual Integration for GrowVRD

This module handles the integration between the Perenual API and GrowVRD's data structure,
mapping external plant data to the internal format and enriching the plant database.
"""
import logging
import uuid
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime
import sys
import os

# Add parent directory to path to properly import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Perenual API client
from api.perenual_api import (
    get_species_list, get_species_details, get_care_guide,
    search_species, PerenualAPIError, find_plants_for_environment
)

# Import core modules (assuming these exist in the core package)
try:
    from core.data_handler import parse_sheet_data, process_plant_data
    from core.oauth_sheets_connector import (
        get_plants_data, append_plant, update_plants_data
    )
except ImportError:
    logging.warning("Core modules not found. Some functionality may be limited.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('perenual_integration')


class MappingError(Exception):
    """Exception raised for errors in the data mapping process"""
    pass


# Mapping constants for converting between different naming conventions
LIGHT_LEVEL_MAP = {
    # Perenual to GrowVRD
    "full_shade": "low",
    "part_shade": "medium",
    "part_sun": "bright_indirect",
    "full_sun": "direct",

    # GrowVRD to Perenual (for reverse lookups)
    "low": "full_shade",
    "medium": "part_shade",
    "bright_indirect": "part_sun",
    "direct": "full_sun"
}

WATER_FREQUENCY_MAP = {
    # Perenual to GrowVRD (days between watering)
    "minimum": 14,
    "average": 7,
    "frequent": 3,

    # Descriptive text mapping
    "minimum_text": "Water when soil is completely dry",
    "average_text": "Water when top inch of soil is dry",
    "frequent_text": "Keep soil consistently moist"
}

DIFFICULTY_MAP = {
    # Perenual maintenance level to GrowVRD difficulty (1-10 scale)
    "low": 2,
    "moderate": 5,
    "high": 8,

    # Default values
    "default": 5
}

MAINTENANCE_MAP = {
    # Perenual maintenance to GrowVRD maintenance
    "low": "low",
    "moderate": "medium",
    "high": "high",

    # Default value
    "default": "medium"
}

HUMIDITY_MAP = {
    # Mapping based on typical plant preferences
    "low": "low",
    "moderate": "medium",
    "high": "high",

    # Default value
    "default": "medium"
}


def map_perenual_to_growvrd(perenual_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Perenual API data to GrowVRD's plant data format.

    Args:
        perenual_data: Plant data from Perenual API

    Returns:
        Mapped data in GrowVRD format

    Raises:
        MappingError: If there are issues with the data mapping
    """
    try:
        # Create a new plant ID in GrowVRD format
        plant_id = f"p{str(perenual_data.get('id')).zfill(5)}"

        # Extract plant name and format it
        common_name = perenual_data.get('common_name', '')
        scientific_name = perenual_data.get('scientific_name', [])
        if isinstance(scientific_name, list) and scientific_name:
            scientific_name = scientific_name[0]

        # Format names for consistency
        formatted_common_name = common_name.lower().replace(' ', '_')
        formatted_scientific_name = str(scientific_name).lower().replace(' ', '_')

        # Map sunlight needs
        sunlight = perenual_data.get('sunlight', [])
        if isinstance(sunlight, str):
            sunlight = [sunlight]

        led_light_requirements = "medium"  # Default
        natural_sunlight_needs = "indirect"  # Default

        if sunlight:
            # Find the lowest light level in the list
            lowest_light = sunlight[0]
            for light in sunlight:
                if light in LIGHT_LEVEL_MAP:
                    if LIGHT_LEVEL_MAP[light] == "low":
                        lowest_light = light
                        break

            led_light_requirements = LIGHT_LEVEL_MAP.get(lowest_light, "medium")
            natural_sunlight_needs = lowest_light.replace('_', ' ')

        # Map watering needs
        watering = perenual_data.get('watering', 'average')
        water_frequency_days = WATER_FREQUENCY_MAP.get(watering, 7)

        # Map difficulty and maintenance
        maintenance_level = perenual_data.get('maintenance', 'moderate')
        difficulty = DIFFICULTY_MAP.get(maintenance_level, DIFFICULTY_MAP['default'])
        maintenance = MAINTENANCE_MAP.get(maintenance_level, MAINTENANCE_MAP['default'])

        # Map other characteristics
        cycle = perenual_data.get('cycle', '')
        drought_tolerant = 7 if 'drought tolerant' in perenual_data.get('attributes', []) else 5

        # Check for indoor compatibility
        indoor_compatible = 'indoor' in perenual_data.get('attributes', [])

        # Determine humidity preference (estimated)
        humidity_preference = HUMIDITY_MAP['default']  # Default
        for attr in perenual_data.get('attributes', []):
            if 'high humidity' in attr.lower():
                humidity_preference = 'high'
                break
            elif 'drought' in attr.lower():
                humidity_preference = 'low'
                break

        # Extract dimensions for sizing
        dimensions = perenual_data.get('dimensions', {})
        max_height = dimensions.get('max_height', {}).get('value', 0)
        size = "medium"  # Default

        if max_height:
            if max_height < 1:
                size = "small"
            elif max_height > 5:
                size = "large"

        # Map to GrowVRD plant structure
        growvrd_plant = {
            "id": plant_id,
            "name": formatted_common_name,
            "scientific_name": formatted_scientific_name,
            "natural_sunlight_needs": natural_sunlight_needs,
            "natural_sunlight_required": "direct" in led_light_requirements,
            "led_light_requirements": led_light_requirements,
            "recommended_light_wattage": 20 if led_light_requirements == "low" else 30 if led_light_requirements == "medium" else 40,
            "led_wattage_min": 15 if led_light_requirements == "low" else 20 if led_light_requirements == "medium" else 30,
            "led_wattage_max": 25 if led_light_requirements == "low" else 35 if led_light_requirements == "medium" else 50,
            "water_frequency_days": water_frequency_days,
            "humidity_preference": humidity_preference,
            "difficulty": difficulty,
            "maintenance": maintenance,
            "indoor_compatible": indoor_compatible,
            "description": perenual_data.get('description', ''),
            "compatible_locations": predict_locations(perenual_data),
            "size": size,
            "temperature_min": 50,  # Default values - can be enhanced with care guide data
            "temperature_max": 80,
            "temperature_ideal": 70,
            "watering_method_preference": "bottom_watering",  # Default - can be enhanced
            "drought_tolerance": drought_tolerant,
            "overwatering_sensitivity": 5,  # Default - can be enhanced
            "soil_preference": "standard_potting_soil",  # Default - can be enhanced
            "soil_replacement_days": 540,  # Default
            "fertilizer_days": 60,  # Default
            "functions": extract_functions(perenual_data),
            "growth_rate_days": 60 if perenual_data.get('growth_rate', '') == 'rapid' else 120,  # Estimated
            "toxic_to_pets": 'toxic to pets' in perenual_data.get('attributes', []),
            "propagation_methods": ["division"],  # Default - can be enhanced
            "common_pests": ["mealybugs", "spider_mites"],  # Default - can be enhanced
            "image_url": perenual_data.get('default_image', {}).get('regular_url', ''),
            "perenual_id": perenual_data.get('id'),
            "perenual_verified": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "searchable_text": f"{common_name} {scientific_name} {cycle} {' '.join(perenual_data.get('attributes', []))}",
            "is_premium_content": False
        }

        return growvrd_plant

    except Exception as e:
        logger.error(f"Error mapping Perenual data: {str(e)}")
        raise MappingError(f"Failed to map Perenual data: {str(e)}")


def predict_locations(perenual_data: Dict[str, Any]) -> List[str]:
    """
    Predict suitable room locations based on plant characteristics.

    Args:
        perenual_data: Plant data from Perenual API

    Returns:
        List of predicted suitable locations
    """
    locations = []
    attributes = [attr.lower() for attr in perenual_data.get('attributes', [])]
    sunlight = perenual_data.get('sunlight', [])

    # Convert string to list if needed
    if isinstance(sunlight, str):
        sunlight = [sunlight]

    # Map sunlight to light level category
    light_levels = [LIGHT_LEVEL_MAP.get(light, "medium") for light in sunlight]

    # Check for bathroom compatibility
    if 'high humidity' in attributes or 'humidity' in attributes:
        locations.append('bathroom')

    # Check for bedroom compatibility
    if 'low' in light_levels or 'medium' in light_levels:
        if 'air purifying' in attributes or not perenual_data.get('toxic_to_pets', False):
            locations.append('bedroom')

    # Check for living room compatibility
    if 'decorative' in attributes or 'large' in attributes or 'bright_indirect' in light_levels:
        locations.append('living_room')

    # Check for kitchen compatibility
    if 'edible' in attributes or 'culinary' in attributes or 'herbs' in attributes:
        locations.append('kitchen')

    # Check for office compatibility
    if 'low' in light_levels or 'small' in attributes or 'air purifying' in attributes:
        locations.append('office')

    # Default if no specific locations identified
    if not locations:
        if 'low' in light_levels:
            locations.extend(['bedroom', 'office'])
        elif 'direct' in light_levels:
            locations.extend(['living_room', 'kitchen'])
        else:
            locations.append('living_room')

    return list(set(locations))  # Remove duplicates


def extract_functions(perenual_data: Dict[str, Any]) -> List[str]:
    """
    Extract plant functions from Perenual attributes.

    Args:
        perenual_data: Plant data from Perenual API

    Returns:
        List of functions in GrowVRD format
    """
    functions = []
    attributes = [attr.lower() for attr in perenual_data.get('attributes', [])]

    # Map common attributes to functions
    mapping = {
        'air purifying': 'air_purification',
        'air purifier': 'air_purification',
        'medicinal': 'medicinal',
        'edible': 'culinary',
        'culinary': 'culinary',
        'herbs': 'culinary',
        'fragrant': 'aromatherapy',
        'ornamental': 'decoration',
        'decorative': 'decoration',
        'showy': 'statement_plant',
        'evergreen': 'evergreen'
    }

    for attr in attributes:
        for key, value in mapping.items():
            if key in attr:
                functions.append(value)

    # Add default function if none identified
    if not functions:
        functions.append('decoration')

    return list(set(functions))  # Remove duplicates


def enrich_plant_with_care_guide(
        plant_data: Dict[str, Any],
        perenual_id: int
) -> Dict[str, Any]:
    """
    Enrich plant data with information from Perenual care guide.

    Args:
        plant_data: Existing plant data in GrowVRD format
        perenual_id: Perenual species ID

    Returns:
        Enhanced plant data with care guide information
    """
    try:
        # Get care guide from Perenual API
        care_guide = get_care_guide(perenual_id)

        # If no care guide found, return the original data
        if not care_guide or 'data' not in care_guide or not care_guide['data']:
            return plant_data

        # Make a copy of the plant data
        enhanced_plant = plant_data.copy()

        # Extract care guide entries
        guide_entries = care_guide['data']

        # Process each care guide section
        for entry in guide_entries:
            section = entry.get('section')
            if not section:
                continue

            content = entry.get('content', '')

            # Process care guide based on section
            if section.lower() == 'watering':
                enhanced_plant = enhance_watering_info(enhanced_plant, content)
            elif section.lower() == 'sunlight':
                enhanced_plant = enhance_light_info(enhanced_plant, content)
            elif section.lower() == 'soil':
                enhanced_plant = enhance_soil_info(enhanced_plant, content)
            elif section.lower() == 'temperature':
                enhanced_plant = enhance_temperature_info(enhanced_plant, content)
            elif section.lower() == 'fertilization':
                enhanced_plant = enhance_fertilizer_info(enhanced_plant, content)
            elif section.lower() == 'pruning':
                enhanced_plant = enhance_maintenance_info(enhanced_plant, content)

        return enhanced_plant

    except PerenualAPIError as e:
        logger.warning(f"Could not get care guide for plant {perenual_id}: {str(e)}")
        return plant_data
    except Exception as e:
        logger.error(f"Error enhancing plant with care guide: {str(e)}")
        return plant_data


def enhance_watering_info(plant: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Extract watering information from care guide content"""
    content_lower = content.lower()

    # Detect watering frequency
    if 'once a week' in content_lower or 'weekly' in content_lower:
        plant['water_frequency_days'] = 7
    elif 'twice a week' in content_lower:
        plant['water_frequency_days'] = 3
    elif 'every two weeks' in content_lower or 'biweekly' in content_lower:
        plant['water_frequency_days'] = 14
    elif 'once a month' in content_lower or 'monthly' in content_lower:
        plant['water_frequency_days'] = 30

    # Detect watering method
    if 'bottom' in content_lower or 'soak' in content_lower:
        plant['watering_method_preference'] = 'bottom_watering'
    elif 'mist' in content_lower or 'spray' in content_lower:
        plant['watering_method_preference'] = 'misting'
    elif 'drip' in content_lower:
        plant['watering_method_preference'] = 'drip_irrigation'

    # Detect sensitivity to overwatering
    if 'root rot' in content_lower or 'overwater' in content_lower:
        plant['overwatering_sensitivity'] = 8

    # Detect drought tolerance
    if 'drought' in content_lower and 'tolerant' in content_lower:
        plant['drought_tolerance'] = 8
    elif 'needs consistent moisture' in content_lower:
        plant['drought_tolerance'] = 3

    return plant


def enhance_light_info(plant: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Extract light requirement information from care guide content"""
    content_lower = content.lower()

    # Detect specific light needs
    if 'full shade' in content_lower or 'dark' in content_lower:
        plant['led_light_requirements'] = 'low'
        plant['natural_sunlight_needs'] = 'low_indirect'
        plant['led_wattage_min'] = 10
        plant['led_wattage_max'] = 20
        plant['recommended_light_wattage'] = 15
    elif 'bright indirect' in content_lower:
        plant['led_light_requirements'] = 'bright_indirect'
        plant['natural_sunlight_needs'] = 'indirect'
        plant['led_wattage_min'] = 20
        plant['led_wattage_max'] = 35
        plant['recommended_light_wattage'] = 25
    elif 'full sun' in content_lower or 'direct sunlight' in content_lower:
        plant['led_light_requirements'] = 'direct'
        plant['natural_sunlight_needs'] = 'direct'
        plant['natural_sunlight_required'] = True
        plant['led_wattage_min'] = 30
        plant['led_wattage_max'] = 50
        plant['recommended_light_wattage'] = 40

    return plant


def enhance_soil_info(plant: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Extract soil preference information from care guide content"""
    content_lower = content.lower()

    # Detect soil type
    if 'well-drain' in content_lower or 'well drain' in content_lower:
        plant['soil_preference'] = 'well_draining_mix'
    elif 'cactus' in content_lower or 'succulent' in content_lower:
        plant['soil_preference'] = 'cactus_mix'
    elif 'peat' in content_lower:
        plant['soil_preference'] = 'peat_based_mix'
    elif 'sandy' in content_lower:
        plant['soil_preference'] = 'sandy_loose_mix'
    elif 'loam' in content_lower:
        plant['soil_preference'] = 'loamy_mix'
    elif 'rich' in content_lower and 'organic' in content_lower:
        plant['soil_preference'] = 'rich_organic_soil'

    # Set soil replacement frequency
    if 'repot' in content_lower and 'annual' in content_lower:
        plant['soil_replacement_days'] = 365
    elif 'repot' in content_lower and 'two years' in content_lower:
        plant['soil_replacement_days'] = 730

    return plant


def enhance_temperature_info(plant: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Extract temperature preference information from care guide content"""
    import re
    content_lower = content.lower()

    # Look for temperature ranges (60-70°F, etc.)
    # Find all patterns like X-Y°F or X-Y degrees F
    temp_ranges = re.findall(r'(\d+)[^\d]+(\d+)[\s]*[°]*[fF]', content_lower)

    if temp_ranges:
        # Use the first range found
        try:
            min_temp, max_temp = int(temp_ranges[0][0]), int(temp_ranges[0][1])
            plant['temperature_min'] = min_temp
            plant['temperature_max'] = max_temp
            plant['temperature_ideal'] = (min_temp + max_temp) // 2
        except (ValueError, IndexError):
            pass

    # Look for qualitative descriptions
    if 'cold' in content_lower and 'sensitive' in content_lower:
        plant['temperature_min'] = 60
    if 'heat' in content_lower and 'sensitive' in content_lower:
        plant['temperature_max'] = 85

    return plant


def enhance_fertilizer_info(plant: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Extract fertilization information from care guide content"""
    content_lower = content.lower()

    # Detect fertilizing frequency
    if 'once a month' in content_lower or 'monthly' in content_lower:
        plant['fertilizer_days'] = 30
    elif 'twice a month' in content_lower or 'bi-weekly' in content_lower or 'biweekly' in content_lower:
        plant['fertilizer_days'] = 14
    elif 'every two months' in content_lower:
        plant['fertilizer_days'] = 60
    elif 'spring and summer' in content_lower:
        plant['fertilizer_days'] = 45  # Approximation for growing season
    elif 'growing season' in content_lower:
        plant['fertilizer_days'] = 45  # Approximation for growing season

    return plant


def enhance_maintenance_info(plant: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Extract maintenance information from care guide content"""
    content_lower = content.lower()

    # Detect maintenance needs
    if 'regular pruning' in content_lower:
        if plant['maintenance'] == 'low':
            plant['maintenance'] = 'medium'

    # Detect propagation methods
    propagation_methods = []
    if 'cutting' in content_lower:
        propagation_methods.append('stem_cutting')
    if 'division' in content_lower:
        propagation_methods.append('division')
    if 'offsets' in content_lower or 'pups' in content_lower:
        propagation_methods.append('offsets')
    if 'seeds' in content_lower:
        propagation_methods.append('seeds')
    if 'layering' in content_lower:
        propagation_methods.append('air_layering')

    if propagation_methods:
        plant['propagation_methods'] = propagation_methods

    # Detect common pests
    pests = []
    if 'spider mite' in content_lower:
        pests.append('spider_mites')
    if 'mealybug' in content_lower:
        pests.append('mealybugs')
    if 'aphid' in content_lower:
        pests.append('aphids')
    if 'scale' in content_lower:
        pests.append('scale')
    if 'whitefl' in content_lower:  # Matches whitefly, whiteflies
        pests.append('whiteflies')

    if pests:
        plant['common_pests'] = pests

    return plant


def search_and_import_plants(
        query: str,
        limit: int = 10,
        save_to_database: bool = False
) -> List[Dict[str, Any]]:
    """
    Search for plants by name and import them into GrowVRD format.

    Args:
        query: Search term
        limit: Maximum number of plants to return
        save_to_database: Whether to save the plants to the database

    Returns:
        List of plants in GrowVRD format
    """
    try:
        # Search Perenual API
        results = search_species(query)

        if 'data' not in results or not results['data']:
            logger.warning(f"No plants found for query: {query}")
            return []

        # Limit number of results
        perenual_plants = results['data'][:limit]

        # Map to GrowVRD format
        growvrd_plants = []

        for perenual_plant in perenual_plants:
            try:
                # Get detailed species information
                species_id = perenual_plant.get('id')
                if not species_id:
                    continue

                species_details = get_species_details(species_id)

                # Map to GrowVRD format
                plant = map_perenual_to_growvrd(species_details)

                # Enrich with care guide information
                plant = enrich_plant_with_care_guide(plant, species_id)

                growvrd_plants.append(plant)

                # Save to database if requested
                if save_to_database:
                    try:
                        append_plant(plant)
                        logger.info(f"Added plant {plant['name']} to database")
                    except Exception as e:
                        logger.error(f"Error saving plant to database: {str(e)}")

            except Exception as e:
                logger.error(f"Error processing plant {perenual_plant.get('id')}: {str(e)}")
                continue

        return growvrd_plants

    except PerenualAPIError as e:
        logger.error(f"API error during search: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Error during search and import: {str(e)}")
        return []


def find_and_import_plants_for_environment(
        location: str,
        light_level: str,
        maintenance_level: str = None,
        limit: int = 10,
        save_to_database: bool = False
) -> List[Dict[str, Any]]:
    """
    Find and import plants suitable for a specific environment.

    Args:
        location: Room location (bathroom, living_room, etc.)
        light_level: Light conditions (low, medium, bright_indirect, direct)
        maintenance_level: Desired maintenance level (low, medium, high)
        limit: Maximum number of plants to return
        save_to_database: Whether to save the plants to the database

    Returns:
        List of suitable plants in GrowVRD format
    """
    try:
        # Find suitable plants using Perenual API
        perenual_plants = find_plants_for_environment(
            location=location,
            light_level=light_level,
            maintenance_level=maintenance_level
        )

        # Limit number of results
        perenual_plants = perenual_plants[:limit]

        # Map to GrowVRD format
        growvrd_plants = []

        for perenual_plant in perenual_plants:
            try:
                # Get detailed species information
                species_id = perenual_plant.get('id')
                if not species_id:
                    continue

                species_details = get_species_details(species_id)

                # Map to GrowVRD format
                plant = map_perenual_to_growvrd(species_details)

                # Enrich with care guide information
                plant = enrich_plant_with_care_guide(plant, species_id)

                # Ensure the plant is compatible with the requested location
                if location not in plant['compatible_locations']:
                    plant['compatible_locations'].append(location)

                growvrd_plants.append(plant)

                # Save to database if requested
                if save_to_database:
                    try:
                        append_plant(plant)
                        logger.info(f"Added plant {plant['name']} to database")
                    except Exception as e:
                        logger.error(f"Error saving plant to database: {str(e)}")

            except Exception as e:
                logger.error(f"Error processing plant {perenual_plant.get('id')}: {str(e)}")
                continue

        return growvrd_plants

    except PerenualAPIError as e:
        logger.error(f"API error during environment search: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Error during environment search and import: {str(e)}")
        return []


def update_plant_database_from_perenual(
        max_plants: int = 100,
        categories: List[str] = None
) -> Tuple[int, int, List[str]]:
    """
    Update the plant database with data from Perenual API.

    Args:
        max_plants: Maximum number of plants to import
        categories: Categories of plants to import (e.g., ['indoor', 'edible'])

    Returns:
        Tuple of (plants_added, plants_updated, errors)
    """
    try:
        # Initialize counters and error list
        plants_added = 0
        plants_updated = 0
        errors = []

        # Get existing plants from the database
        try:
            existing_plants = get_plants_data()
            existing_perenual_ids = set()

            for plant in existing_plants:
                if 'perenual_id' in plant and plant['perenual_id']:
                    existing_perenual_ids.add(str(plant['perenual_id']))

            logger.info(f"Found {len(existing_plants)} existing plants, {len(existing_perenual_ids)} with Perenual IDs")

        except Exception as e:
            logger.error(f"Error retrieving existing plants: {str(e)}")
            existing_plants = []
            existing_perenual_ids = set()

        # Set up filters for Perenual API
        filters = {}
        if categories:
            for category in categories:
                if category == 'indoor':
                    filters['indoor'] = 1
                elif category == 'edible':
                    filters['edible'] = 1

        # Get plants from Perenual API
        page = 1
        plants_imported = 0

        while plants_imported < max_plants:
            try:
                # Get a page of species
                species_list = get_species_list(page=page, per_page=30, filters=filters)

                if 'data' not in species_list or not species_list['data']:
                    logger.info("No more plants to import")
                    break

                species_page = species_list['data']

                # Process each species
                for species in species_page:
                    # Check if we've reached the limit
                    if plants_imported >= max_plants:
                        break

                    try:
                        species_id = species.get('id')
                        if not species_id:
                            continue

                        # Skip if we already have this plant
                        if str(species_id) in existing_perenual_ids:
                            logger.debug(f"Skipping existing plant: {species.get('common_name')} (ID: {species_id})")
                            continue

                        # Get detailed information
                        species_details = get_species_details(species_id)

                        # Map to GrowVRD format
                        plant = map_perenual_to_growvrd(species_details)

                        # Enrich with care guide
                        plant = enrich_plant_with_care_guide(plant, species_id)

                        # Add to database
                        try:
                            append_plant(plant)
                            plants_added += 1
                            plants_imported += 1
                            logger.info(f"Added plant: {plant['name']} (ID: {plant['id']})")
                        except Exception as e:
                            error_msg = f"Error adding plant {plant['name']}: {str(e)}"
                            logger.error(error_msg)
                            errors.append(error_msg)

                    except Exception as e:
                        error_msg = f"Error processing species {species.get('id')}: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                        continue

                # Check if there are more pages
                if page >= species_list.get('last_page', 1):
                    logger.info("Reached last page of results")
                    break

                page += 1

            except PerenualAPIError as e:
                error_msg = f"API error on page {page}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                break

        return plants_added, plants_updated, errors

    except Exception as e:
        logger.error(f"Error updating database: {str(e)}")
        return 0, 0, [f"General error: {str(e)}"]


def create_test_plant():
    """
    Create a test plant to verify Perenual API integration is working.

    Returns:
        Mapped plant data or None if the API connection fails
    """
    try:
        # Test the connection to Perenual API
        species_list = get_species_list(per_page=1)

        if 'data' not in species_list or not species_list['data']:
            logger.warning("No plants found in API test")
            return None

        species = species_list['data'][0]
        species_id = species.get('id')

        if not species_id:
            logger.warning("No species ID found in API test")
            return None

        # Get detailed species information
        species_details = get_species_details(species_id)

        # Map to GrowVRD format
        plant = map_perenual_to_growvrd(species_details)

        # Enrich with care guide
        plant = enrich_plant_with_care_guide(plant, species_id)

        logger.info(f"Successfully created test plant: {plant['name']}")
        return plant

    except PerenualAPIError as e:
        logger.error(f"API error during test: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error creating test plant: {str(e)}")
        return None


# If run directly, perform a test
if __name__ == "__main__":
    test_plant = create_test_plant()

    if test_plant:
        print("API integration test successful!")
        print(f"Test plant: {test_plant['name']} ({test_plant['scientific_name']})")
        print(f"Description: {test_plant['description'][:100]}...")
    else:
        print("API integration test failed. Check the logs for details.")
"""
Functions to add to perenual_integration.py for improved plant recommendations
These functions enhance the integration between Perenual API and GrowVRD.
"""
import logging
from typing import Dict, List, Any, Optional, Union

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('perenual_integration')


def is_plant_appropriate_for_location(plant: Dict[str, Any], location: str) -> bool:
    """
    Check if a plant is appropriate for a specific location.

    Args:
        plant: Plant data dictionary
        location: Location string (kitchen, living_room, etc.)

    Returns:
        Boolean indicating whether the plant is appropriate
    """
    # First check if the plant explicitly lists this location
    compatible_locations = plant.get('compatible_locations', [])
    if isinstance(compatible_locations, str):
        compatible_locations = compatible_locations.split(',')

    if location in compatible_locations:
        return True

    # Extract useful information from the plant
    plant_name = plant.get('name', '').lower().replace('_', ' ')
    scientific_name = plant.get('scientific_name', '').lower().replace('_', ' ')
    description = plant.get('description', '').lower()
    humidity_pref = plant.get('humidity_preference', '').lower()
    light_needs = plant.get('natural_sunlight_needs', '').lower()
    size = plant.get('size', '').lower()
    toxic = plant.get('toxic_to_pets', False)

    functions = plant.get('functions', [])
    if isinstance(functions, str):
        functions = functions.split(',')
    functions = [f.lower() for f in functions]

    # Location-specific logic
    if location == 'kitchen':
        # Kitchen plants should be:
        # 1. Herbs or edible plants
        if 'herb' in plant_name or 'culinary' in functions or 'herb' in plant_name:
            return True

        # 2. Compact size
        if 'small' in size:
            return True

        # 3. Tolerant of temperature changes
        if 'medium' in humidity_pref or 'low' in humidity_pref:
            return True

        # Common kitchen-appropriate houseplants
        kitchen_plants = [
            'pothos', 'spider plant', 'snake plant', 'aloe vera',
            'jade plant', 'peace lily', 'mint', 'basil', 'thyme',
            'rosemary', 'parsley', 'chive', 'sage', 'air plant'
        ]
        if any(kp in plant_name or kp in scientific_name for kp in kitchen_plants):
            return True

        return False

    elif location == 'bathroom':
        # Bathroom plants should be:
        # 1. Thrive in high humidity
        if 'high' in humidity_pref:
            return True

        # 2. Tolerate low light
        if 'low' in light_needs or 'indirect' in light_needs:
            return True

        # Common bathroom-appropriate plants
        bathroom_plants = [
            'peace lily', 'boston fern', 'spider plant', 'orchid',
            'pothos', 'snake plant', 'air plant', 'aloe vera'
        ]
        if any(bp in plant_name or bp in scientific_name for bp in bathroom_plants):
            return True

        return False

    elif location == 'bedroom':
        # Bedroom plants should be:
        # 1. Air purifying (preferable)
        if 'air_purification' in functions or 'air purifying' in description:
            return True

        # 2. Non-toxic preferred
        if not toxic:
            # Also check light needs for bedrooms
            if 'low' in light_needs or 'medium' in light_needs:
                return True

        # 3. Calming or sleep-promoting mentioned
        if 'calming' in description or 'sleep' in description:
            return True

        # Common bedroom plants
        bedroom_plants = [
            'snake plant', 'peace lily', 'spider plant', 'pothos',
            'aloe vera', 'lavender', 'jasmine', 'english ivy'
        ]
        if any(bp in plant_name or bp in scientific_name for bp in bedroom_plants):
            return True

        return False

    elif location == 'living_room':
        # Living room plants can be:
        # 1. Statement or decorative plants
        if 'statement_plant' in functions or 'decoration' in functions:
            return True

        # 2. Medium or large size
        if 'medium' in size or 'large' in size:
            return True

        # 3. Attractive appearance
        if 'beautiful' in description or 'attractive' in description:
            return True

        # Common living room plants
        living_room_plants = [
            'monstera', 'fiddle leaf fig', 'rubber plant', 'palm',
            'dracaena', 'snake plant', 'pothos', 'philodendron',
            'zz plant', 'bird of paradise'
        ]
        if any(lp in plant_name or lp in scientific_name for lp in living_room_plants):
            return True

        return False

    elif location == 'office':
        # Office plants should be:
        # 1. Low maintenance
        if 'low' in plant.get('maintenance', '').lower():
            return True

        # 2. Can handle low light
        if 'low' in light_needs:
            return True

        # 3. Air purifying
        if 'air_purification' in functions:
            return True

        # Common office plants
        office_plants = [
            'snake plant', 'zz plant', 'pothos', 'peace lily',
            'spider plant', 'philodendron', 'jade plant'
        ]
        if any(op in plant_name or op in scientific_name for op in office_plants):
            return True

        return False

    elif location == 'balcony':
        # Balcony plants:
        # 1. Can handle direct sunlight or more exposure
        if 'direct' in light_needs or 'full sun' in light_needs:
            return True

        # 2. More weather-resistant
        if 'outdoor' in description or 'hardy' in description:
            return True

        # Common balcony plants
        balcony_plants = [
            'geranium', 'lavender', 'succulent', 'cactus', 'herbs',
            'mint', 'basil', 'rosemary', 'thyme', 'sage',
            'aloe vera', 'jade plant'
        ]
        if any(bp in plant_name or bp in scientific_name for bp in balcony_plants):
            return True

        return False

    # If we have no specific logic for this location, default to true
    return True


def map_light_conditions(light_level: str) -> List[str]:
    """
    Map GrowVRD light level strings to Perenual API-compatible light conditions.

    Args:
        light_level: Light level string (low, medium, bright_indirect, direct)

    Returns:
        List of equivalent Perenual API light conditions
    """
    mapping = {
        'low': ['full_shade', 'shade'],
        'medium': ['part_shade', 'filtered_shade'],
        'bright_indirect': ['part_sun', 'filtered_shade'],
        'direct': ['full_sun', 'sun']
    }

    return mapping.get(light_level.lower(), ['part_shade'])  # Default to part shade if unknown


def enhance_find_plants_for_environment(
        location: str,
        light_level: str,
        maintenance_level: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Enhanced version of find_plants_for_environment that adds location filtering.

    Args:
        location: Room location (bathroom, living_room, etc.)
        light_level: Light conditions (low, medium, bright_indirect, direct)
        maintenance_level: Desired maintenance level (low, medium, high)

    Returns:
        List of plants in GrowVRD format suitable for the environment
    """
    from api.perenual_api import search_species, get_species_details, find_plants_for_environment

    try:
        # First get plants using the existing function
        plants = find_plants_for_environment(
            location=location,
            light_level=light_level,
            maintenance_level=maintenance_level
        )

        # Then filter them to ensure they're appropriate for the location
        filtered_plants = [p for p in plants if is_plant_appropriate_for_location(p, location)]

        # If we have too few results after filtering, use a location-specific search
        if len(filtered_plants) < 3:
            location_search_terms = {
                "kitchen": "herb culinary kitchen plant",
                "living_room": "houseplant decorative living room",
                "bedroom": "air purifying calming bedroom plant",
                "bathroom": "humidity tolerant bathroom plant",
                "office": "low light desk office plant",
                "balcony": "outdoor container balcony plant"
            }

            search_term = location_search_terms.get(location, "indoor plant")

            # Import the search_and_import_plants function
            from api.perenual_integration import search_and_import_plants

            # Get additional plants
            additional_plants = search_and_import_plants(
                query=search_term,
                limit=5,
                save_to_database=False
            )

            # Filter them for location appropriateness
            additional_filtered = [p for p in additional_plants if is_plant_appropriate_for_location(p, location)]

            # Combine the results, avoiding duplicates
            existing_ids = [p.get('id') for p in filtered_plants]
            for plant in additional_filtered:
                if plant.get('id') not in existing_ids:
                    filtered_plants.append(plant)

        return filtered_plants

    except Exception as e:
        logger.error(f"Error in enhanced_find_plants_for_environment: {str(e)}")
        return []


def filter_plants_by_pet_safety(plants: List[Dict[str, Any]], pet_friendly: bool = True) -> List[Dict[str, Any]]:
    """
    Filter plants based on their safety for pets.

    Args:
        plants: List of plant dictionaries
        pet_friendly: Whether to return only pet-friendly plants

    Returns:
        Filtered list of plants
    """
    if not pet_friendly:
        return plants

    return [p for p in plants if not p.get('toxic_to_pets', True)]


def filter_plants_by_air_purifying(plants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter plants to only include those with air purifying properties.

    Args:
        plants: List of plant dictionaries

    Returns:
        Filtered list of plants
    """
    return [p for p in plants if 'air_purification' in (
        p.get('functions', []) if isinstance(p.get('functions', []), list)
        else p.get('functions', '').split(',')
    )]


def get_recommended_plants_for_location(location: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get highly recommended plants for a specific location without other filters.

    Args:
        location: Room location (bathroom, living_room, etc.)
        limit: Maximum number of plants to return

    Returns:
        List of recommended plants for the location
    """
    # Import the necessary functions
    from api.perenual_api import search_species, get_species_details
    from api.perenual_integration import search_and_import_plants

    # Define search terms based on location
    location_search_terms = {
        "kitchen": "kitchen herb culinary",
        "living_room": "living room houseplant decorative",
        "bedroom": "bedroom air purifying calming",
        "bathroom": "bathroom humidity tolerant",
        "office": "office low light desk",
        "balcony": "balcony outdoor container"
    }

    search_term = location_search_terms.get(location, "indoor plant")

    try:
        # Search for plants using the location-specific terms
        plants = search_and_import_plants(
            query=search_term,
            limit=limit * 2,  # Get extra plants to allow for filtering
            save_to_database=False
        )

        # Filter to ensure they're appropriate for the location
        filtered_plants = [p for p in plants if is_plant_appropriate_for_location(p, location)]

        # Return up to the limit
        return filtered_plants[:limit]

    except Exception as e:
        logger.error(f"Error in get_recommended_plants_for_location: {str(e)}")
        return []