"""
Enhanced mock data provider for GrowVRD development and testing
Loads data from local TSV files rather than hardcoded data
"""
import os
import csv
import logging
from typing import List, Dict, Any
from pathlib import Path

# Set up logging
logger = logging.getLogger('mock_data')

# Define the path to data files
DATA_DIR = Path(__file__).parent.parent / "data"


def _load_tsv_file(filename: str) -> List[Dict[str, Any]]:
    """
    Load a TSV file into a list of dictionaries

    Args:
        filename: Name of the TSV file to load

    Returns:
        List of dictionaries containing the data
    """
    file_path = DATA_DIR / filename

    # Fallback to hardcoded mock data if file doesn't exist
    if not file_path.exists():
        logger.warning(f"Data file {file_path} not found, using hardcoded mock data")
        return []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            return list(reader)
    except Exception as e:
        logger.error(f"Error loading data from {file_path}: {str(e)}")
        return []


# Sample plant data matching your schema - used as fallback
MOCK_PLANTS = [
    {
        "id": "p001",
        "name": "snake_plant",
        "scientific_name": "dracaena_trifasciata",
        "natural_sunlight_needs": "low_indirect",
        "natural_sunlight_required": "FALSE",
        "led_light_requirements": "low",
        "recommended_light_wattage": "15",
        "led_wattage_min": "10",
        "led_wattage_max": "20",
        "water_frequency_days": "14",
        "humidity_preference": "low",
        "difficulty": "1",
        "maintenance": "low",
        "indoor_compatible": "TRUE",
        "description": "Hardy, air-purifying plant with vertical leaves. Tolerates neglect.",
        "compatible_locations": "office,bedroom",
        "size": "medium",
        "temperature_min": "50",
        "temperature_max": "90",
        "temperature_ideal": "70",
        "watering_method_preference": "bottom_watering",
        "drought_tolerance": "9",
        "overwatering_sensitivity": "6",
        "soil_preference": "sandy_loose_mix",
        "soil_replacement_days": "900",
        "fertilizer_days": "90",
        "functions": "air_purification,decoration,night_oxygen",
        "growth_rate_days": "90",
        "toxic_to_pets": "TRUE",
        "propagation_methods": "division,leaf_cutting",
        "common_pests": "mealybugs,spider_mites",
        "image_url": "https://example.com/plants/snake_plant.jpg"
    },
    {
        "id": "p002",
        "name": "pothos",
        "scientific_name": "epipremnum_aureum",
        "natural_sunlight_needs": "indirect",
        "natural_sunlight_required": "FALSE",
        "led_light_requirements": "medium",
        "recommended_light_wattage": "20",
        "led_wattage_min": "15",
        "led_wattage_max": "25",
        "water_frequency_days": "7",
        "humidity_preference": "moderate",
        "difficulty": "2",
        "maintenance": "low",
        "indoor_compatible": "TRUE",
        "description": "Trailing vine with heart-shaped leaves. Adapts to various light conditions.",
        "compatible_locations": "shelf,hanging_planter,living_room",
        "size": "medium",
        "temperature_min": "55",
        "temperature_max": "90",
        "temperature_ideal": "70",
        "watering_method_preference": "top_watering",
        "drought_tolerance": "7",
        "overwatering_sensitivity": "6",
        "soil_preference": "standard_potting_soil",
        "soil_replacement_days": "540",
        "fertilizer_days": "30",
        "functions": "air_purification,decoration",
        "growth_rate_days": "30",
        "toxic_to_pets": "TRUE",
        "propagation_methods": "stem_cutting",
        "common_pests": "mealybugs,spider_mites",
        "image_url": "https://example.com/plants/pothos.jpg"
    },
    {
        "id": "p003",
        "name": "peace_lily",
        "scientific_name": "spathiphyllum",
        "natural_sunlight_needs": "low_indirect",
        "natural_sunlight_required": "FALSE",
        "led_light_requirements": "medium",
        "recommended_light_wattage": "20",
        "led_wattage_min": "15",
        "led_wattage_max": "30",
        "water_frequency_days": "7",
        "humidity_preference": "high",
        "difficulty": "4",
        "maintenance": "moderate",
        "indoor_compatible": "TRUE",
        "description": "Elegant flowering plant known for air-purifying qualities. Tolerates low light conditions.",
        "compatible_locations": "office,bedroom,bathroom",
        "size": "medium",
        "temperature_min": "60",
        "temperature_max": "80",
        "temperature_ideal": "70",
        "watering_method_preference": "top_watering",
        "drought_tolerance": "4",
        "overwatering_sensitivity": "8",
        "soil_preference": "standard_potting_soil",
        "soil_replacement_days": "360",
        "fertilizer_days": "30",
        "functions": "air_purification,decoration",
        "growth_rate_days": "30",
        "toxic_to_pets": "TRUE",
        "propagation_methods": "division",
        "common_pests": "mealybugs,spider_mites",
        "image_url": "https://example.com/plants/peace_lily.jpg"
    }
]

# Sample product data
MOCK_PRODUCTS = [
    {
        "id": "pr001",
        "name": "ceramic_pot",
        "category": "pot",
        "subcategory": "tabletop",
        "price": "19.99",
        "amazon_link": "https://amazon.com/...",
        "description": "Stylish ceramic pot with drainage",
        "compatible_locations": "kitchen,living_room,bathroom",
        "size_compatibility": "small",
        "replacement_days": "0",
        "application_frequency_days": "0",
        "plant_ids": "p001,p002,p003",
        "watering_method": "",
        "temperature_control_range": "",
        "average_rating": "4.7",
        "review_count": "356",
        "in_stock": "TRUE",
        "image_url": "https://example.com/products/ceramic_pot.jpg"
    },
    {
        "id": "pr002",
        "name": "pre_mix_soil",
        "category": "soil",
        "subcategory": "all_purpose",
        "price": "14.99",
        "amazon_link": "https://amazon.com/...",
        "description": "Pre-mixed soil for indoor plants",
        "compatible_locations": "all",
        "size_compatibility": "all",
        "replacement_days": "540",
        "application_frequency_days": "0",
        "plant_ids": "all",
        "watering_method": "",
        "temperature_control_range": "",
        "average_rating": "4.5",
        "review_count": "289",
        "in_stock": "TRUE",
        "image_url": "https://example.com/products/soil.jpg"
    }
]

# Sample kit data
MOCK_KITS = [
    {
        "id": "k001",
        "name": "bathroom_oasis",
        "locations": "bathroom",
        "natural_light_conditions": "low",
        "led_light_conditions": "medium",
        "humidity_level": "high",
        "size_constraint": "small",
        "difficulty": "beginner",
        "temperature_range": "70_to_80f",
        "watering_frequency_days": "7",
        "watering_method": "misting",
        "plant_ids": "p003",
        "required_product_categories": "pot,soil,mister",
        "soil_maintenance_days": "365",
        "fertilizer_days": "30",
        "functions": "aesthetic_enhancement,air_purification",
        "price": "75",
        "difficulty_explanation": "Plants thrive in high humidity with minimal light and care",
        "setup_time_minutes": "30",
        "maintenance_time_minutes_weekly": "15",
        "image_url": "https://example.com/kits/bathroom.jpg"
    },
    {
        "id": "k002",
        "name": "bedroom_relaxation_kit",
        "locations": "bedroom",
        "natural_light_conditions": "low",
        "led_light_conditions": "medium",
        "humidity_level": "moderate",
        "size_constraint": "medium",
        "difficulty": "beginner",
        "temperature_range": "65_to_75f",
        "watering_frequency_days": "7",
        "watering_method": "top_watering",
        "plant_ids": "p001,p003",
        "required_product_categories": "pot,soil,watering_can",
        "soil_maintenance_days": "540",
        "fertilizer_days": "60",
        "functions": "relaxation,air_purification",
        "price": "50",
        "difficulty_explanation": "Low-light plants with easy, calming care routines",
        "setup_time_minutes": "30",
        "maintenance_time_minutes_weekly": "15",
        "image_url": "https://example.com/kits/bedroom.jpg"
    }
]


def get_mock_plants():
    """Return mock plant data, loading from file if available"""
    plants = _load_tsv_file("GrowVRD_Plants")
    return plants if plants else MOCK_PLANTS.copy()


def get_mock_products():
    """Return mock product data, loading from file if available"""
    products = _load_tsv_file("GrowVRD_Products")
    return products if products else MOCK_PRODUCTS.copy()


def get_mock_kits():
    """Return mock kit data, loading from file if available"""
    kits = _load_tsv_file("GrowVRD_Kits")
    return kits if kits else MOCK_KITS.copy()


def get_mock_users():
    """Return mock user data, loading from file if available"""
    return _load_tsv_file("GrowVRD_Users")


def get_mock_plant_products():
    """Return mock plant-product junction data, loading from file if available"""
    return _load_tsv_file("GrowVRD_PlantProducts")


def get_mock_user_plants():
    """Return mock user-plant junction data, loading from file if available"""
    return _load_tsv_file("GrowVRD_UserPlants")