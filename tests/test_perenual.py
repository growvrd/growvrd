#!/usr/bin/env python
"""
Test script for Perenual API integration
"""
import os
import logging
import json
from dotenv import load_dotenv
from api.perenual_api import get_species_list, get_species_details, PerenualAPIError
from api.perenual_integration import (
    map_perenual_to_growvrd,
    search_and_import_plants,
    create_test_plant
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_perenual')

# Load environment variables
load_dotenv()


def test_api_connection():
    """Test basic API connection"""
    try:
        result = get_species_list(per_page=1)
        if 'data' in result and result['data']:
            logger.info(f"API connection successful. Sample plant: {result['data'][0]['common_name']}")
            return True
        else:
            logger.error("API connection failed: No data returned")
            return False
    except PerenualAPIError as e:
        logger.error(f"API connection failed: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"API connection failed with unexpected error: {str(e)}")
        return False


def test_mapping():
    """Test mapping from Perenual to GrowVRD format"""
    try:
        # Get a test species
        species_list = get_species_list(per_page=1)
        if 'data' not in species_list or not species_list['data']:
            logger.error("API connection failed: No data returned")
            return False

        species_id = species_list['data'][0]['id']
        species_details = get_species_details(species_id)

        # Map to GrowVRD format
        growvrd_plant = map_perenual_to_growvrd(species_details)

        # Verify essential fields are present
        required_fields = [
            'id', 'name', 'scientific_name', 'description', 'natural_sunlight_needs',
            'led_light_requirements', 'water_frequency_days', 'compatible_locations'
        ]

        missing_fields = [field for field in required_fields if field not in growvrd_plant]

        if missing_fields:
            logger.error(f"Mapping failed: Missing fields: {missing_fields}")
            return False

        logger.info(f"Mapping successful for plant: {growvrd_plant['name']}")

        # Pretty print the mapped plant for inspection
        print(json.dumps(growvrd_plant, indent=2))

        return True

    except Exception as e:
        logger.error(f"Mapping test failed: {str(e)}")
        return False


def test_search():
    """Test plant search functionality"""
    try:
        # Test with a common plant name
        query = "monstera"
        plants = search_and_import_plants(query, limit=2, save_to_database=False)

        if not plants:
            logger.error(f"Search failed: No plants found for query '{query}'")
            return False

        logger.info(f"Search successful. Found {len(plants)} plants for query '{query}'")

        # Print first plant name and description
        print(f"Sample plant: {plants[0]['name']}")
        print(f"Description: {plants[0]['description'][:100]}...")

        return True

    except Exception as e:
        logger.error(f"Search test failed: {str(e)}")
        return False


def run_all_tests():
    """Run all tests and report results"""
    print("\n===== PERENUAL API INTEGRATION TESTS =====\n")

    # Check if API key is set
    api_key = os.getenv("PERENUAL_API_KEY")
    if not api_key:
        print("ERROR: PERENUAL_API_KEY environment variable not set.")
        print("Please set it in the .env file and try again.")
        return

    # Test API connection
    print("\n----- Testing API Connection -----")
    connection_result = test_api_connection()
    print(f"Connection test {'PASSED' if connection_result else 'FAILED'}")

    if not connection_result:
        print("\nAPI connection failed. Cannot continue with other tests.")
        return

    # Test mapping
    print("\n----- Testing Data Mapping -----")
    mapping_result = test_mapping()
    print(f"Mapping test {'PASSED' if mapping_result else 'FAILED'}")

    # Test search
    print("\n----- Testing Plant Search -----")
    search_result = test_search()
    print(f"Search test {'PASSED' if search_result else 'FAILED'}")

    # Summary
    print("\n===== TEST SUMMARY =====")
    print(f"Connection: {'✅' if connection_result else '❌'}")
    print(f"Mapping:    {'✅' if mapping_result else '❌'}")
    print(f"Search:     {'✅' if search_result else '❌'}")

    if connection_result and mapping_result and search_result:
        print("\n🎉 All tests PASSED! The Perenual API integration is working correctly.")
    else:
        print("\n⚠️ Some tests FAILED. Please check the logs for details.")


if __name__ == "__main__":
    run_all_tests()