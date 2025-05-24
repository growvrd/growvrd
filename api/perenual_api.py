"""
Perenual API Client for GrowVRD

This module provides functions to interact with the Perenual API
for plant data, care guides, and species information.
"""
import os
import logging
import time
import requests
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('perenual_api')

# Constants
API_BASE_URL = "https://perenual.com/api"
DEFAULT_API_KEY = os.getenv("PERENUAL_API_KEY", "")

# Rate limiting settings
RATE_LIMIT_REQUESTS = 50  # Default for free tier
RATE_LIMIT_PERIOD = 60  # seconds (per minute)
_last_request_time = 0
_request_count = 0


class PerenualAPIError(Exception):
    """Exception raised for errors in the Perenual API"""
    pass


def _rate_limit() -> None:
    """
    Implements rate limiting to avoid exceeding API limits.
    Sleeps if necessary to ensure we don't exceed the rate limit.
    """
    global _last_request_time, _request_count

    current_time = time.time()
    time_passed = current_time - _last_request_time

    # Reset counter if we're in a new period
    if time_passed > RATE_LIMIT_PERIOD:
        _last_request_time = current_time
        _request_count = 0
        return

    # Check if we're about to exceed the rate limit
    if _request_count >= RATE_LIMIT_REQUESTS:
        # Calculate how long to sleep
        sleep_time = RATE_LIMIT_PERIOD - time_passed
        if sleep_time > 0:
            logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        # Reset counter for the new period
        _last_request_time = time.time()
        _request_count = 0
    else:
        # Increment request counter
        _request_count += 1


def make_api_request(
        endpoint: str,
        params: Dict[str, Any] = None,
        api_key: str = None,
        method: str = "GET"
) -> Dict[str, Any]:
    """
    Make a request to the Perenual API with rate limiting.

    Args:
        endpoint: API endpoint (without the base URL)
        params: Query parameters to include in the request
        api_key: API key to use (defaults to env variable)
        method: HTTP method (GET, POST, etc.)

    Returns:
        JSON response as a dictionary

    Raises:
        PerenualAPIError: If the API request fails
    """
    # Use default API key if none provided
    if api_key is None:
        api_key = DEFAULT_API_KEY

    if not api_key:
        raise PerenualAPIError("No API key provided. Set PERENUAL_API_KEY environment variable.")

    # Initialize parameters dictionary if None
    if params is None:
        params = {}

    # Add API key to parameters
    params["key"] = api_key

    # Apply rate limiting
    _rate_limit()

    # Construct full URL
    url = f"{API_BASE_URL}/{endpoint}"

    try:
        logger.debug(f"Making {method} request to {endpoint}")

        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, json=params, timeout=10)
        else:
            raise PerenualAPIError(f"Unsupported HTTP method: {method}")

        # Check for HTTP errors
        response.raise_for_status()

        # Parse JSON response
        data = response.json()

        # Check for API errors
        if "error" in data:
            raise PerenualAPIError(f"API error: {data['error']}")

        return data

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        raise PerenualAPIError(f"Request failed: {str(e)}")
    except ValueError as e:
        logger.error(f"Invalid JSON response: {str(e)}")
        raise PerenualAPIError(f"Invalid JSON response: {str(e)}")


def get_species_list(
        page: int = 1,
        per_page: int = 30,
        filters: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Get a list of plant species with optional filtering.

    Args:
        page: Page number for pagination
        per_page: Number of results per page
        filters: Dictionary of filter criteria
            Possible keys:
                - watering: str (minimum, average, frequent)
                - sunlight: str (full_shade, part_shade, part_sun, full_sun)
                - cycle: str (perennial, annual, biennial, biannual)
                - indoor: bool (1 for indoor plants)
                - edible: bool (1 for edible plants)
                - poisonous: bool (1 for poisonous plants)
                - growth_rate: str (slow, moderate, fast)
                - maintenance: str (low, medium, high)

    Returns:
        API response with list of species
    """
    # Initialize parameters
    params = {
        "page": page,
        "per_page": per_page
    }

    # Add filters if provided
    if filters:
        params.update(filters)

    return make_api_request("species-list", params)


def get_species_details(species_id: int) -> Dict[str, Any]:
    """
    Get detailed information about a specific plant species.

    Args:
        species_id: The ID of the species to retrieve

    Returns:
        API response with species details
    """
    return make_api_request(f"species/details/{species_id}")


def get_care_guide(species_id: int) -> Dict[str, Any]:
    """
    Get care guide for a specific plant species.

    Args:
        species_id: The ID of the species to retrieve care info for

    Returns:
        API response with care guide details
    """
    return make_api_request(f"species-care-guide-list", {"species_id": species_id})


def search_species(query: str, page: int = 1, per_page: int = 30) -> Dict[str, Any]:
    """
    Search for plant species by name.

    Args:
        query: Search term (plant name)
        page: Page number for pagination
        per_page: Number of results per page

    Returns:
        API response with search results
    """
    params = {
        "q": query,
        "page": page,
        "per_page": per_page
    }

    return make_api_request("species-list", params)


def get_indoor_light_requirements() -> Dict[str, Any]:
    """
    Get a list of indoor light requirement options for plants.

    Returns:
        API response with light requirements
    """
    return make_api_request("indoor-light-requirements")


def get_watering_frequencies() -> Dict[str, Any]:
    """
    Get a list of watering frequency options for plants.

    Returns:
        API response with watering frequencies
    """
    return make_api_request("watering-list")


def get_watering_by_species(species_id: int) -> Dict[str, Any]:
    """
    Get watering information for a specific species.

    Args:
        species_id: The ID of the species

    Returns:
        API response with watering details
    """
    return make_api_request(f"species-watering/{species_id}")


# Helper functions for common tasks

def get_all_species_by_filter(
        filters: Dict[str, Any] = None,
        max_pages: int = 5
) -> List[Dict[str, Any]]:
    """
    Get all species matching specified filters (up to a limit).

    Args:
        filters: Dictionary of filter criteria
        max_pages: Maximum number of pages to retrieve

    Returns:
        List of plant species
    """
    all_species = []
    current_page = 1

    while current_page <= max_pages:
        response = get_species_list(page=current_page, filters=filters)

        # Add species from current page
        species_list = response.get("data", [])
        all_species.extend(species_list)

        # Check if we've reached the last page
        if current_page >= response.get("last_page", 1):
            break

        current_page += 1

    return all_species


def find_plants_for_environment(
        location: str,
        light_level: str,
        maintenance_level: str = None,
        indoor_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Find plants suitable for a specific environment.

    Args:
        location: Room location (bathroom, living_room, etc.)
        light_level: Light conditions (low, medium, bright_indirect, direct)
        maintenance_level: Desired maintenance level (low, medium, high)
        indoor_only: Whether to only include indoor plants

    Returns:
        List of suitable plant species
    """
    # Map GrowVRD light levels to Perenual sunlight values
    light_map = {
        "low": ["full_shade", "part_shade"],
        "medium": ["part_shade", "part_sun"],
        "bright_indirect": ["part_sun"],
        "direct": ["full_sun"]
    }

    # Map GrowVRD maintenance levels to Perenual
    maintenance_map = {
        "low": "low",
        "medium": "moderate",
        "high": "high"
    }

    # Initialize filters
    filters = {}

    # Add indoor filter if requested
    if indoor_only:
        filters["indoor"] = 1

    # Add maintenance filter if provided
    if maintenance_level and maintenance_level in maintenance_map:
        filters["maintenance"] = maintenance_map[maintenance_level]

    # Get plants for each applicable light level
    all_matched_plants = []

    for sunlight in light_map.get(light_level, []):
        filters["sunlight"] = sunlight
        plants = get_all_species_by_filter(filters)
        all_matched_plants.extend(plants)

    # Add humidity/moisture considerations based on location
    # For future enhancement: filter further by location-specific requirements

    return all_matched_plants


# Initialize when the module is loaded
if __name__ == "__main__":
    # Test the API if run directly
    if not DEFAULT_API_KEY:
        logger.warning("No API key found. Set PERENUAL_API_KEY in environment variables.")
    else:
        try:
            species = get_species_list(per_page=5)
            logger.info(f"API connection successful. Found {species.get('total', 0)} plant species.")
        except PerenualAPIError as e:
            logger.error(f"API test failed: {str(e)}")