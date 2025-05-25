"""
GrowVRD API Integration Package

This package contains integrations with external APIs for plant data.

Modules:
- perenual_api: Perenual plant database API client
- perenual_integration: Integration between Perenual and GrowVRD data formats
"""

__version__ = "1.0.0"

# Import key functions for easy access
try:
    from .perenual_api import search_species, get_species_details
    from .perenual_integration import search_and_import_plants

    __all__ = [
        'search_species',
        'get_species_details',
        'search_and_import_plants'
    ]
except ImportError as e:
    # Handle import errors gracefully during development
    print(f"Warning: Some API modules not available: {e}")
    __all__ = []