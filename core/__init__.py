"""
GrowVRD Core Package

This package contains the core functionality for the GrowVRD plant recommendation system.

Modules:
- data_handler: Data parsing and validation
- filters: Plant filtering algorithms
- mock_data: Mock data for development
- oauth_sheets_connector: Google Sheets connection
- recommendation_engine: Main recommendation logic
"""

__version__ = "1.0.0"
__author__ = "GrowVRD Team"

# Import key functions for easy access
try:
    from .mock_data import get_mock_plants, get_mock_products, get_mock_kits
    from .filters import filter_plants
    from .recommendation_engine import get_recommendations

    __all__ = [
        'get_mock_plants',
        'get_mock_products',
        'get_mock_kits',
        'filter_plants',
        'get_recommendations'
    ]
except ImportError as e:
    # Handle import errors gracefully during development
    print(f"Warning: Some core modules not available: {e}")
    __all__ = []