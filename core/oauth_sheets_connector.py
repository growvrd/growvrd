import os
import pickle
import logging
import time
import functools
import threading
import json
from typing import List, Dict, Any, Optional, Union, Callable, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import gspread
import pandas as pd
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound, APIError

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('sheets_connector')

# Add the parent directory to path to properly import config
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import config

    # Use mock data in development mode
    USE_MOCK_DATA = config.ENVIRONMENT == "development" or os.getenv("USE_MOCK_DATA") == "true"

    if USE_MOCK_DATA:
        try:
            from core.mock_data import get_mock_plants, get_mock_products, get_mock_kits

            logger.info("Using mock data in development mode")
        except ImportError:
            logger.warning("Mock data module not found, will try to use real Google Sheets")
            USE_MOCK_DATA = False
except ImportError:
    logger.warning("Could not import config, using defaults")
    USE_MOCK_DATA = os.getenv("USE_MOCK_DATA") == "true"

# Constants
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


# Enhanced cache with TTL and auto-cleanup
class EnhancedCache:
    """
    Enhanced caching system with TTL, auto-cleanup, and memory management.
    """

    def __init__(self, max_size: int = 100):
        self._cache: Dict[str, Tuple[Any, float, datetime]] = {}  # (value, priority, timestamp)
        self._lock = threading.RLock()
        self._max_size = max_size
        self._cleanup_threshold = max_size * 0.8
        self._last_cleanup = datetime.now()
        self._cleanup_interval = timedelta(minutes=10)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the cache with automatic expiration check"""
        with self._lock:
            if key not in self._cache:
                return default

            value, priority, timestamp = self._cache[key]

            # Check if the entry has expired
            if timestamp + timedelta(seconds=priority) < datetime.now():
                del self._cache[key]
                return default

            # Update priority based on access frequency
            self._cache[key] = (value, priority * 1.1, timestamp)
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a value in the cache with a TTL"""
        with self._lock:
            # Perform cleanup if needed
            self._maybe_cleanup()

            # Add or update the entry
            self._cache[key] = (value, ttl, datetime.now())

    def _maybe_cleanup(self) -> None:
        """Perform cache cleanup if needed"""
        # Check if it's time for periodic cleanup
        if len(self._cache) > self._cleanup_threshold or \
                datetime.now() - self._last_cleanup > self._cleanup_interval:

            self._last_cleanup = datetime.now()

            # Remove expired entries
            now = datetime.now()
            expired_keys = [
                k for k, (_, ttl, timestamp) in self._cache.items()
                if timestamp + timedelta(seconds=ttl) < now
            ]

            for k in expired_keys:
                del self._cache[k]

            # If still too large, remove least recently used entries
            if len(self._cache) > self._max_size:
                # Sort by priority (lower priority = less valuable)
                sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
                # Remove oldest 20% of entries
                remove_count = max(1, int(len(self._cache) * 0.2))
                for k, _ in sorted_items[:remove_count]:
                    del self._cache[k]

            logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired items, current size: {len(self._cache)}")

    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        """Return the number of items in the cache"""
        return len(self._cache)


# Create a global cache instance
_enhanced_cache = EnhancedCache(max_size=200)

# Rate limiting tracking
_rate_limits = {
    'free': {'requests_per_day': 50, 'requests_per_minute': 5},
    'subscriber': {'requests_per_day': 500, 'requests_per_minute': 20}
}

_user_request_counts = defaultdict(lambda: {'daily': 0, 'minute': 0, 'last_reset': datetime.now()})
_rate_limit_lock = threading.Lock()


# Configuration
class SheetConfig:
    """Configuration for Google Sheets connection"""
    # Project root is two directories up from this file
    PROJECT_ROOT = Path(__file__).parent.parent

    # Paths can be overridden by environment variables
    TOKEN_PATH = os.environ.get('GROWVRD_TOKEN_PATH', str(PROJECT_ROOT / 'token.pickle'))

    # Look for credentials in multiple locations
    _possible_credential_paths = [
        PROJECT_ROOT / 'client_secrets.json',
        PROJECT_ROOT / '.venv/client_secrets.json',
        PROJECT_ROOT.parent / 'client_secrets.json',
        Path('client_secrets.json'),
        Path('../client_secrets.json'),
        Path('../.venv/client_secrets.json')
    ]

    # Use the first credential file that exists, or default to the env var or project root
    CREDENTIALS_PATH = os.environ.get('GROWVRD_CREDENTIALS_PATH', None)
    if not CREDENTIALS_PATH or not Path(CREDENTIALS_PATH).exists():
        for path in _possible_credential_paths:
            if path.exists():
                CREDENTIALS_PATH = str(path)
                logger.info(f"Found credentials at: {CREDENTIALS_PATH}")
                break
        if not CREDENTIALS_PATH:
            CREDENTIALS_PATH = str(PROJECT_ROOT / 'client_secrets.json')
            logger.warning(f"No credentials file found, using default path: {CREDENTIALS_PATH}")

    # Sheet names
    PLANTS_SHEET = 'GrowVRD_Plants'
    PRODUCTS_SHEET = 'GrowVRD_Products'
    KITS_SHEET = 'GrowVRD_Kits'
    USERS_SHEET = 'GrowVRD_Users'
    PLANT_PRODUCTS_SHEET = 'GrowVRD_PlantProducts'
    USER_PLANTS_SHEET = 'GrowVRD_UserPlants'

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds


class GoogleSheetsConnectionError(Exception):
    """Exception raised for errors connecting to Google Sheets"""
    pass


class GoogleSheetsDataError(Exception):
    """Exception raised for errors with data from Google Sheets"""
    pass


def smart_cached(ttl: int = 300, shared: bool = True, key_prefix: str = "", key_func: Optional[Callable] = None):
    """
    Smart caching decorator with dynamic TTL and customizable cache keys.

    Args:
        ttl: Cache timeout in seconds (can be adjusted based on data type)
        shared: Whether to use the global cache or a function-specific cache
        key_prefix: Optional prefix for the cache key to group related items
        key_func: Optional function to generate a custom cache key

    Returns:
        Decorated function with caching
    """

    def decorator(func):
        # Create a function-specific cache if not shared
        if not shared:
            func_cache = EnhancedCache(max_size=50)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Skip caching if explicitly requested
            if kwargs.get('skip_cache', False):
                if 'skip_cache' in kwargs:
                    del kwargs['skip_cache']
                return func(*args, **kwargs)

            # Generate a cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Create a deterministic string from the arguments
                arg_key = ":".join(str(arg) for arg in args)
                kwarg_key = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{key_prefix}:{func.__name__}:{arg_key}:{kwarg_key}"

            # Determine which cache to use
            cache = _enhanced_cache if shared else func_cache

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_value

            # Call the function
            result = func(*args, **kwargs)

            # Store in cache
            # For frequently changing data types, adjust TTL
            adjusted_ttl = ttl
            if func.__name__ == 'get_user_plants_data':
                # User plants change more frequently, shorter TTL
                adjusted_ttl = min(ttl, 60)
            elif func.__name__ == 'get_plants_data':
                # Plant data is more stable, longer TTL
                adjusted_ttl = max(ttl, 600)

            cache.set(cache_key, result, adjusted_ttl)
            logger.debug(f"Cache miss for {func.__name__}, cached with TTL {adjusted_ttl}s")

            return result

        # Add cache management methods to the wrapped function
        wrapper.clear_cache = lambda: _enhanced_cache.clear() if shared else func_cache.clear()
        wrapper.cache_info = lambda: {"size": len(_enhanced_cache if shared else func_cache)}

        return wrapper

    return decorator


def clear_cache():
    """Clear the in-memory cache"""
    _enhanced_cache.clear()
    logger.info("Cache cleared")


def get_sheets_client(mock_client=None) -> gspread.Client:
    """
    Connect to Google Sheets using OAuth and return the client.

    Args:
        mock_client: Optional mock client for testing

    Returns:
        gspread.Client: Authenticated Google Sheets client

    Raises:
        GoogleSheetsConnectionError: If connection fails
    """
    # Allow injection of mock client for testing
    if mock_client is not None:
        logger.info("Using mock client for testing")
        return mock_client

    try:
        token_path = Path(SheetConfig.TOKEN_PATH)
        credentials_path = Path(SheetConfig.CREDENTIALS_PATH)

        logger.info(f"Looking for token at {token_path}")
        logger.info(f"Using credentials at {credentials_path}")

        creds = None

        # Load existing credentials if available
        if token_path.exists():
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
                logger.info("Loaded credentials from token file")
            except (pickle.PickleError, EOFError) as e:
                logger.warning(f"Error loading token file: {str(e)}")
                # Continue with None credentials

        # Refresh or create credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired credentials")
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Error refreshing credentials: {str(e)}")
                    creds = None

            # If still no valid credentials, authenticate with OAuth flow
            if not creds or not creds.valid:
                logger.info("Starting OAuth flow for new credentials")

                if not credentials_path.exists():
                    # Check all possible credentials paths
                    found_creds = False
                    for path in SheetConfig._possible_credential_paths:
                        if path.exists():
                            credentials_path = path
                            found_creds = True
                            logger.info(f"Found credentials at alternate location: {credentials_path}")
                            break

                    if not found_creds:
                        credential_search_paths = "\n- ".join([str(p) for p in SheetConfig._possible_credential_paths])
                        raise GoogleSheetsConnectionError(
                            f"Credentials file not found. Searched in:\n- {credential_search_paths}\n"
                            f"Download client_secrets.json from Google Cloud Console."
                        )

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(credentials_path), SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    logger.info("Successfully authenticated with OAuth")
                except Exception as e:
                    raise GoogleSheetsConnectionError(f"OAuth authentication failed: {str(e)}")

            # Save credentials for future use
            try:
                # Create parent directories if they don't exist
                token_path.parent.mkdir(parents=True, exist_ok=True)

                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
                logger.info(f"Saved credentials to {token_path}")
            except Exception as e:
                logger.warning(f"Failed to save credentials: {str(e)}")

        # Create gspread client
        client = gspread.authorize(creds)
        logger.info("Successfully connected to Google Sheets")
        return client

    except Exception as e:
        if isinstance(e, GoogleSheetsConnectionError):
            raise
        raise GoogleSheetsConnectionError(f"Failed to connect to Google Sheets: {str(e)}")


def check_rate_limit(email: str) -> bool:
    """
    Check if a user has exceeded their rate limit based on subscription.

    Args:
        email: User's email address

    Returns:
        True if under limit, False if rate limited
    """
    with _rate_limit_lock:
        subscription = get_user_subscription_status(email)
        limits = _rate_limits.get(subscription, _rate_limits['free'])

        # Get user's request counts
        counts = _user_request_counts[email]
        now = datetime.now()

        # Reset daily counter if it's a new day
        if now.date() != counts['last_reset'].date():
            counts['daily'] = 0

        # Reset minute counter if it's been more than a minute
        if (now - counts['last_reset']).total_seconds() > 60:
            counts['minute'] = 0

        counts['last_reset'] = now

        # Check limits
        if counts['daily'] >= limits['requests_per_day']:
            logger.warning(f"User {email} exceeded daily request limit")
            return False

        if counts['minute'] >= limits['requests_per_minute']:
            logger.warning(f"User {email} exceeded per-minute request limit")
            return False

        # Increment counters
        counts['daily'] += 1
        counts['minute'] += 1

        return True


def get_sheet_data(sheet_name: str, worksheet_index: int = 0) -> List[Dict[str, Any]]:
    """
    Retrieve data from a specific Google Sheet with retries.

    Args:
        sheet_name: Name of the Google Sheet
        worksheet_index: Index of the worksheet (default is 0 for first sheet)

    Returns:
        List of dictionaries containing the sheet data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    retry_count = 0
    last_error = None

    while retry_count < SheetConfig.MAX_RETRIES:
        try:
            client = get_sheets_client()

            # Open the spreadsheet
            try:
                spreadsheet = client.open(sheet_name)
            except SpreadsheetNotFound:
                raise GoogleSheetsDataError(f"Spreadsheet '{sheet_name}' not found")

            # Get the worksheet
            try:
                if worksheet_index == 0:
                    worksheet = spreadsheet.sheet1
                else:
                    worksheet = spreadsheet.get_worksheet(worksheet_index)
                    if worksheet is None:
                        raise GoogleSheetsDataError(f"Worksheet index {worksheet_index} not found in '{sheet_name}'")
            except WorksheetNotFound:
                raise GoogleSheetsDataError(f"Worksheet at index {worksheet_index} not found in '{sheet_name}'")

            # Get all records
            records = worksheet.get_all_records()

            if not records:
                logger.warning(f"No data found in {sheet_name}, worksheet {worksheet_index}")
                return []

            logger.info(f"Successfully retrieved {len(records)} records from {sheet_name}")
            return records

        except (APIError, ConnectionError) as e:
            retry_count += 1
            last_error = e
            logger.warning(f"API error on attempt {retry_count}/{SheetConfig.MAX_RETRIES}: {str(e)}")

            if retry_count < SheetConfig.MAX_RETRIES:
                time.sleep(SheetConfig.RETRY_DELAY)
        except GoogleSheetsDataError:
            # Don't retry for data-specific errors
            raise
        except Exception as e:
            retry_count += 1
            last_error = e
            logger.warning(f"Error on attempt {retry_count}/{SheetConfig.MAX_RETRIES}: {str(e)}")

            if retry_count < SheetConfig.MAX_RETRIES:
                time.sleep(SheetConfig.RETRY_DELAY)

    # If we've exhausted all retries
    error_msg = f"Failed to retrieve data from {sheet_name} after {SheetConfig.MAX_RETRIES} attempts"
    if last_error:
        error_msg += f": {str(last_error)}"
    raise GoogleSheetsDataError(error_msg)


@smart_cached(ttl=600, key_prefix="plants")
def get_plants_data() -> List[Dict[str, Any]]:
    """
    Retrieve plant data from Google Sheets with advanced caching.

    Returns:
        List of dictionaries containing plant data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    # Use mock data in development
    if USE_MOCK_DATA:
        try:
            return get_mock_plants()
        except Exception as e:
            logger.warning(f"Error getting mock plant data: {str(e)}")
            # Continue to try real Google Sheets

    try:
        records = get_sheet_data(SheetConfig.PLANTS_SHEET)
        return records
    except Exception as e:
        logger.error(f"Error retrieving plant data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving plant data: {str(e)}")


@smart_cached(ttl=600, key_prefix="products")
def get_products_data() -> List[Dict[str, Any]]:
    """
    Retrieve product data from Google Sheets with advanced caching.

    Returns:
        List of dictionaries containing product data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    # Use mock data in development
    if USE_MOCK_DATA:
        try:
            return get_mock_products()
        except Exception as e:
            logger.warning(f"Error getting mock product data: {str(e)}")
            # Continue to try real Google Sheets

    try:
        records = get_sheet_data(SheetConfig.PRODUCTS_SHEET)
        return records
    except Exception as e:
        logger.error(f"Error retrieving product data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving product data: {str(e)}")


@smart_cached(ttl=600, key_prefix="kits")
def get_kits_data() -> List[Dict[str, Any]]:
    """
    Retrieve kit data from Google Sheets with advanced caching.

    Returns:
        List of dictionaries containing kit data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    # Use mock data in development
    if USE_MOCK_DATA:
        try:
            return get_mock_kits()
        except Exception as e:
            logger.warning(f"Error getting mock kit data: {str(e)}")
            # Continue to try real Google Sheets

    try:
        records = get_sheet_data(SheetConfig.KITS_SHEET)
        return records
    except Exception as e:
        logger.error(f"Error retrieving kit data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving kit data: {str(e)}")


@smart_cached(ttl=60, key_prefix="users")  # Short TTL for user data
def get_users_data() -> List[Dict[str, Any]]:
    """
    Retrieve user data from Google Sheets with advanced caching.

    Returns:
        List of dictionaries containing user data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    try:
        records = get_sheet_data(SheetConfig.USERS_SHEET)
        return records
    except Exception as e:
        logger.error(f"Error retrieving user data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving user data: {str(e)}")


@smart_cached(ttl=300, key_prefix="plant_products")
def get_plant_products_data() -> List[Dict[str, Any]]:
    """
    Retrieve plant-product junction data from Google Sheets with advanced caching.

    Returns:
        List of dictionaries containing plant-product relationship data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    try:
        records = get_sheet_data(SheetConfig.PLANT_PRODUCTS_SHEET)
        return records
    except Exception as e:
        logger.error(f"Error retrieving plant-product data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving plant-product data: {str(e)}")


@smart_cached(ttl=60, key_prefix="user_plants")  # User plants change frequently
def get_user_plants_data() -> List[Dict[str, Any]]:
    """
    Retrieve user-plant junction data from Google Sheets with advanced caching.

    Returns:
        List of dictionaries containing user-plant relationship data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    try:
        records = get_sheet_data(SheetConfig.USER_PLANTS_SHEET)
        return records
    except Exception as e:
        logger.error(f"Error retrieving user-plant data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving user-plant data: {str(e)}")


def get_all_data() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Optimized function to fetch plants, products, and kits data in one batch.
    This reduces the number of separate API calls.

    Returns:
        Tuple containing (plants_data, products_data, kits_data)

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    if USE_MOCK_DATA:
        try:
            return (get_mock_plants(), get_mock_products(), get_mock_kits())
        except Exception as e:
            logger.warning(f"Error getting mock data: {str(e)}")

    try:
        # Get a single sheets client
        client = get_sheets_client()

        # Batch open the spreadsheets to reduce API calls
        plants_sheet = client.open(SheetConfig.PLANTS_SHEET)
        products_sheet = client.open(SheetConfig.PRODUCTS_SHEET)
        kits_sheet = client.open(SheetConfig.KITS_SHEET)

        # Get all worksheets
        plants_worksheet = plants_sheet.sheet1
        products_worksheet = products_sheet.sheet1
        kits_worksheet = kits_sheet.sheet1

        # Fetch data
        plants_data = plants_worksheet.get_all_records()
        products_data = products_worksheet.get_all_records()
        kits_data = kits_worksheet.get_all_records()

        return plants_data, products_data, kits_data

    except Exception as e:
        logger.error(f"Error retrieving batch data: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving batch data: {str(e)}")


def get_plants_dataframe() -> pd.DataFrame:
    """
    Retrieve plant data as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing plant data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    plants_data = get_plants_data()
    return pd.DataFrame(plants_data)


def get_products_dataframe() -> pd.DataFrame:
    """
    Retrieve product data as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing product data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    products_data = get_products_data()
    return pd.DataFrame(products_data)


def get_kits_dataframe() -> pd.DataFrame:
    """
    Retrieve kit data as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing kit data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    kits_data = get_kits_data()
    return pd.DataFrame(kits_data)


def get_users_dataframe() -> pd.DataFrame:
    """
    Retrieve user data as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing user data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    users_data = get_users_data()
    return pd.DataFrame(users_data)


def get_plant_products_dataframe() -> pd.DataFrame:
    """
    Retrieve plant-product junction data as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing plant-product relationship data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    plant_products_data = get_plant_products_data()
    return pd.DataFrame(plant_products_data)


def get_user_plants_dataframe() -> pd.DataFrame:
    """
    Retrieve user-plant junction data as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing user-plant relationship data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    user_plants_data = get_user_plants_data()
    return pd.DataFrame(user_plants_data)


def update_sheet_data(sheet_name: str, data: List[Dict[str, Any]], worksheet_index: int = 0) -> bool:
    """
    Update data in a Google Sheet.

    Args:
        sheet_name: Name of the Google Sheet
        data: List of dictionaries to write to the sheet
        worksheet_index: Index of the worksheet (default is 0 for first sheet)

    Returns:
        bool: True if successful, False otherwise

    Raises:
        GoogleSheetsDataError: If update fails
    """
    if not data:
        logger.warning("No data provided for update")
        return False

    try:
        client = get_sheets_client()

        # Open the spreadsheet
        try:
            spreadsheet = client.open(sheet_name)
        except SpreadsheetNotFound:
            raise GoogleSheetsDataError(f"Spreadsheet '{sheet_name}' not found")

        # Get the worksheet
        try:
            if worksheet_index == 0:
                worksheet = spreadsheet.sheet1
            else:
                worksheet = spreadsheet.get_worksheet(worksheet_index)
                if worksheet is None:
                    raise GoogleSheetsDataError(f"Worksheet index {worksheet_index} not found in '{sheet_name}'")
        except WorksheetNotFound:
            raise GoogleSheetsDataError(f"Worksheet at index {worksheet_index} not found in '{sheet_name}'")

        # Extract all field names from the data
        all_fields = set()
        for item in data:
            all_fields.update(item.keys())

        # Create header row and data rows
        header = list(all_fields)
        rows = []
        for item in data:
            row = [item.get(field, '') for field in header]
            rows.append(row)

        # Clear existing data and update with new data
        worksheet.clear()
        worksheet.append_row(header)

        # Batch update rows for better performance
        if rows:
            worksheet.append_rows(rows)

        # Clear the cache for this sheet
        cache_key = f"get_{sheet_name.lower().replace('growvrd_', '')}_data"

        # Clear related caches
        clear_cache()
        logger.debug(f"Cleared cache after updating {sheet_name}")

        logger.info(f"Successfully updated {len(rows)} rows in {sheet_name}")
        return True

    except Exception as e:
        error_msg = f"Failed to update {sheet_name}: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


def update_plants_data(plants_data: List[Dict[str, Any]]) -> bool:
    """
    Update plant data in Google Sheets.

    Args:
        plants_data: List of plant dictionaries

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If update fails
    """
    result = update_sheet_data(SheetConfig.PLANTS_SHEET, plants_data)
    # Explicitly clear the plants cache
    _enhanced_cache.clear()
    return result


def update_products_data(products_data: List[Dict[str, Any]]) -> bool:
    """
    Update product data in Google Sheets.

    Args:
        products_data: List of product dictionaries

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If update fails
    """
    result = update_sheet_data(SheetConfig.PRODUCTS_SHEET, products_data)
    # Explicitly clear the products cache
    _enhanced_cache.clear()
    return result


def update_kits_data(kits_data: List[Dict[str, Any]]) -> bool:
    """
    Update kit data in Google Sheets.

    Args:
        kits_data: List of kit dictionaries

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If update fails
    """
    result = update_sheet_data(SheetConfig.KITS_SHEET, kits_data)
    # Explicitly clear the kits cache
    _enhanced_cache.clear()
    return result


def update_users_data(users_data: List[Dict[str, Any]]) -> bool:
    """
    Update user data in Google Sheets.

    Args:
        users_data: List of user dictionaries

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If update fails
    """
    result = update_sheet_data(SheetConfig.USERS_SHEET, users_data)
    # Explicitly clear the users cache
    _enhanced_cache.clear()
    return result


def update_plant_products_data(plant_products_data: List[Dict[str, Any]]) -> bool:
    """
    Update plant-product junction data in Google Sheets.

    Args:
        plant_products_data: List of plant-product relationship dictionaries

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If update fails
    """
    result = update_sheet_data(SheetConfig.PLANT_PRODUCTS_SHEET, plant_products_data)
    # Explicitly clear related caches
    _enhanced_cache.clear()
    return result


def update_user_plants_data(user_plants_data: List[Dict[str, Any]]) -> bool:
    """
    Update user-plant junction data in Google Sheets.

    Args:
        user_plants_data: List of user-plant relationship dictionaries

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If update fails
    """
    result = update_sheet_data(SheetConfig.USER_PLANTS_SHEET, user_plants_data)
    # Explicitly clear related caches
    _enhanced_cache.clear()
    return result


def append_sheet_row(sheet_name: str, row_data: Dict[str, Any], worksheet_index: int = 0) -> bool:
    """
    Append a single row to a Google Sheet.

    Args:
        sheet_name: Name of the Google Sheet
        row_data: Dictionary containing the row data
        worksheet_index: Index of the worksheet (default is 0 for first sheet)

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    if not row_data:
        logger.warning("No data provided for append")
        return False

    try:
        client = get_sheets_client()

        # Open the spreadsheet
        try:
            spreadsheet = client.open(sheet_name)
        except SpreadsheetNotFound:
            raise GoogleSheetsDataError(f"Spreadsheet '{sheet_name}' not found")

        # Get the worksheet
        try:
            if worksheet_index == 0:
                worksheet = spreadsheet.sheet1
            else:
                worksheet = spreadsheet.get_worksheet(worksheet_index)
                if worksheet is None:
                    raise GoogleSheetsDataError(f"Worksheet index {worksheet_index} not found in '{sheet_name}'")
        except WorksheetNotFound:
            raise GoogleSheetsDataError(f"Worksheet at index {worksheet_index} not found in '{sheet_name}'")

        # Get the header row
        header = worksheet.row_values(1)
        if not header:
            raise GoogleSheetsDataError(f"Header row not found in {sheet_name}")

        # Prepare row data in the correct order
        row = [row_data.get(field, '') for field in header]

        # Append the row
        worksheet.append_row(row)

        # Clear related caches
        _enhanced_cache.clear()
        logger.debug(f"Cleared cache after appending to {sheet_name}")

        logger.info(f"Successfully appended row to {sheet_name}")
        return True

    except Exception as e:
        error_msg = f"Failed to append row to {sheet_name}: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


def append_plant(plant_data: Dict[str, Any]) -> bool:
    """
    Append a single plant to the plants sheet.

    Args:
        plant_data: Dictionary containing plant data

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    return append_sheet_row(SheetConfig.PLANTS_SHEET, plant_data)


def append_product(product_data: Dict[str, Any]) -> bool:
    """
    Append a single product to the products sheet.

    Args:
        product_data: Dictionary containing product data

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    return append_sheet_row(SheetConfig.PRODUCTS_SHEET, product_data)


def append_kit(kit_data: Dict[str, Any]) -> bool:
    """
    Append a single kit to the kits sheet.

    Args:
        kit_data: Dictionary containing kit data

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    return append_sheet_row(SheetConfig.KITS_SHEET, kit_data)


def append_user(user_data: Dict[str, Any]) -> bool:
    """
    Append a single user to the users sheet.

    Args:
        user_data: Dictionary containing user data

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    return append_sheet_row(SheetConfig.USERS_SHEET, user_data)


def append_plant_product(plant_product_data: Dict[str, Any]) -> bool:
    """
    Append a single plant-product relationship to the plant-products junction sheet.

    Args:
        plant_product_data: Dictionary containing plant-product relationship data

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    return append_sheet_row(SheetConfig.PLANT_PRODUCTS_SHEET, plant_product_data)


def append_user_plant(user_plant_data: Dict[str, Any]) -> bool:
    """
    Append a single user-plant relationship to the user-plants junction sheet.

    Args:
        user_plant_data: Dictionary containing user-plant relationship data

    Returns:
        bool: True if successful

    Raises:
        GoogleSheetsDataError: If append fails
    """
    return append_sheet_row(SheetConfig.USER_PLANTS_SHEET, user_plant_data)


@smart_cached(ttl=60, key_prefix="user")  # Short TTL for user data
def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific user by email with enhanced caching.

    Args:
        email: User's email address

    Returns:
        User data dictionary or None if not found

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    try:
        users_data = get_users_data()
        for user in users_data:
            if user.get('email', '').lower() == email.lower():
                return user
        return None
    except Exception as e:
        logger.error(f"Error retrieving user by email: {str(e)}")
        raise GoogleSheetsDataError(f"Error retrieving user by email: {str(e)}")


@smart_cached(ttl=60, key_prefix="subscription")  # Short TTL for subscription status
def get_user_subscription_status(email: str) -> str:
    """
    Get subscription status for a user with enhanced caching.

    Args:
        email: User's email address

    Returns:
        Subscription status ('free' or 'subscriber'), defaults to 'free' if user not found
    """
    try:
        user = get_user_by_email(email)
        if user and user.get('subscription_status'):
            return user['subscription_status'].lower()
        return 'free'  # Default to free tier
    except Exception as e:
        logger.warning(f"Error getting subscription status, defaulting to free: {str(e)}")
        return 'free'


def update_user_kit(email: str, kit_id: str, kit_data: Dict[str, Any]) -> bool:
    """
    Update or add a custom kit for a subscriber user.

    Args:
        email: User's email address
        kit_id: ID of the kit to update
        kit_data: Kit data to save

    Returns:
        True if successful, False if user not found or not a subscriber

    Raises:
        GoogleSheetsDataError: If update fails
    """
    try:
        # Get all users
        users_data = get_users_data()
        updated = False

        for i, user in enumerate(users_data):
            if user.get('email', '').lower() == email.lower():
                # Check subscription status
                if user.get('subscription_status', '').lower() != 'subscriber':
                    logger.warning(f"Non-subscriber attempted to save kit: {email}")
                    return False

                # Update or add the kit
                custom_kits = user.get('custom_configurations', {})
                if not isinstance(custom_kits, dict):
                    try:
                        if isinstance(custom_kits, str):
                            custom_kits = json.loads(custom_kits)
                        else:
                            custom_kits = {}
                    except json.JSONDecodeError:
                        custom_kits = {}

                custom_kits[kit_id] = kit_data
                users_data[i]['custom_configurations'] = custom_kits
                updated = True
                break

        if not updated:
            logger.warning(f"User not found for kit update: {email}")
            return False

        # Update the users sheet
        result = update_users_data(users_data)

        # Clear user-specific cache
        _enhanced_cache.clear()

        return result

    except Exception as e:
        error_msg = f"Failed to update user kit: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


def verify_user_credentials(email: str, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Verify user credentials for API authentication.

    Args:
        email: User's email address
        token: Authentication token or password

    Returns:
        Tuple of (is_authenticated, user_data)

    Raises:
        GoogleSheetsDataError: If verification fails
    """
    try:
        user = get_user_by_email(email)

        if not user:
            logger.warning(f"Authentication failed: User not found: {email}")
            return False, None

        # In a real implementation, you would use proper password hashing
        # This is just a placeholder for the structure
        stored_token = user.get('auth_token', '')

        if stored_token and stored_token == token:
            return True, user

        logger.warning(f"Authentication failed: Invalid token for {email}")
        return False, None

    except Exception as e:
        error_msg = f"Authentication error: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


@smart_cached(ttl=300, key_prefix="user_plants")
def get_plants_for_user(email: str) -> List[Dict[str, Any]]:
    """
    Get all plants owned by a specific user with personalized data and enhanced caching.

    Args:
        email: User's email address

    Returns:
        List of plant dictionaries with personalization data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    try:
        # Get the user to verify they exist
        user = get_user_by_email(email)
        if not user:
            logger.warning(f"User not found: {email}")
            return []

        # Get user's plants from the junction table
        user_plants_data = get_user_plants_data()
        user_id = user.get('id', '')

        if not user_id:
            logger.warning(f"User has no ID: {email}")
            return []

        # Filter user's plants
        user_plants = [p for p in user_plants_data if p.get('user_id') == user_id]

        if not user_plants:
            logger.info(f"User has no plants: {email}")
            return []

        # Get full plant data
        plants_data = get_plants_data()
        plant_dict = {p.get('id', ''): p for p in plants_data}

        # Combine plant data with personalization
        result = []
        for user_plant in user_plants:
            plant_id = user_plant.get('plant_id', '')
            if not plant_id or plant_id not in plant_dict:
                continue

            # Start with base plant data
            full_plant = plant_dict[plant_id].copy()

            # Add personalized data
            full_plant['nickname'] = user_plant.get('nickname', '')
            full_plant['acquisition_date'] = user_plant.get('acquisition_date', '')
            full_plant['last_watered'] = user_plant.get('last_watered', '')
            full_plant['last_fertilized'] = user_plant.get('last_fertilized', '')
            full_plant['health_status'] = user_plant.get('health_status', '')
            full_plant['location_in_home'] = user_plant.get('location_in_home', '')
            full_plant['days_since_watered'] = user_plant.get('days_since_watered', 0)

            result.append(full_plant)

        return result

    except Exception as e:
        error_msg = f"Error retrieving plants for user: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


@smart_cached(ttl=300, key_prefix="plant_products")
def get_products_for_plant(plant_id: str) -> List[Dict[str, Any]]:
    """
    Get all compatible products for a specific plant with compatibility data and enhanced caching.

    Args:
        plant_id: ID of the plant

    Returns:
        List of product dictionaries with compatibility data

    Raises:
        GoogleSheetsDataError: If data retrieval fails
    """
    try:
        # Get plant-product relationships
        plant_products_data = get_plant_products_data()

        # Filter by plant ID
        plant_products = [pp for pp in plant_products_data if pp.get('plant_id') == plant_id]

        if not plant_products:
            logger.info(f"No products found for plant: {plant_id}")
            return []

        # Get full product data
        products_data = get_products_data()
        product_dict = {p.get('id', ''): p for p in products_data}

        # Combine product data with compatibility information
        result = []
        for plant_product in plant_products:
            product_id = plant_product.get('product_id', '')
            if not product_id or product_id not in product_dict:
                continue

            # Start with base product data
            full_product = product_dict[product_id].copy()

            # Add compatibility data
            full_product['compatibility_rating'] = plant_product.get('compatibility_rating', 0)
            full_product['primary_purpose'] = plant_product.get('primary_purpose', '')
            full_product['recommended_usage'] = plant_product.get('recommended_usage', '')
            full_product['compatibility_notes'] = plant_product.get('compatibility_notes', '')

            result.append(full_product)

        # Sort by compatibility rating (highest first)
        result.sort(key=lambda x: x.get('compatibility_rating', 0), reverse=True)

        return result

    except Exception as e:
        error_msg = f"Error retrieving products for plant: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


def update_user_plant_status(email: str, plant_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update status information for a specific plant owned by a user.

    Args:
        email: User's email address
        plant_id: ID of the plant to update
        update_data: Dictionary with fields to update (e.g., last_watered, health_status)

    Returns:
        True if successful, False otherwise

    Raises:
        GoogleSheetsDataError: If update fails
    """
    try:
        # Get user ID
        user = get_user_by_email(email)
        if not user:
            logger.warning(f"User not found: {email}")
            return False

        user_id = user.get('id', '')
        if not user_id:
            logger.warning(f"User has no ID: {email}")
            return False

        # Get user-plant junction data
        user_plants_data = get_user_plants_data()
        updated = False

        # Find and update the specific plant
        for i, user_plant in enumerate(user_plants_data):
            if user_plant.get('user_id') == user_id and user_plant.get('plant_id') == plant_id:
                # Update fields
                for key, value in update_data.items():
                    if key in user_plant:
                        user_plants_data[i][key] = value
                updated = True
                break

        if not updated:
            logger.warning(f"Plant {plant_id} not found for user {email}")
            return False

        # Update the sheet
        result = update_user_plants_data(user_plants_data)

        # Clear user-specific plant cache
        cache_key = f"user_plants:{email}"
        _enhanced_cache.clear()

        return result

    except Exception as e:
        error_msg = f"Failed to update plant status: {str(e)}"
        logger.error(error_msg)
        raise GoogleSheetsDataError(error_msg)


def bulk_update_sheets(updates: Dict[str, List[Dict[str, Any]]]) -> Dict[str, bool]:
    """
    Update multiple sheets in a single batch operation to reduce API calls.

    Args:
        updates: Dictionary mapping sheet names to lists of data dictionaries
            Example: {'GrowVRD_Plants': [plant1, plant2], 'GrowVRD_Products': [product1]}

    Returns:
        Dictionary mapping sheet names to success status (True/False)
    """
    results = {}
    client = None

    try:
        # Get a single client for all operations
        client = get_sheets_client()

        for sheet_name, data in updates.items():
            if not data:
                logger.warning(f"No data provided for {sheet_name}, skipping")
                results[sheet_name] = False
                continue

            try:
                # Open the spreadsheet
                try:
                    spreadsheet = client.open(sheet_name)
                    worksheet = spreadsheet.sheet1
                except SpreadsheetNotFound:
                    logger.error(f"Spreadsheet '{sheet_name}' not found")
                    results[sheet_name] = False
                    continue

                # Extract all field names
                all_fields = set()
                for item in data:
                    all_fields.update(item.keys())

                header = list(all_fields)
                rows = []
                for item in data:
                    row = [item.get(field, '') for field in header]
                    rows.append(row)

                # Update the sheet
                worksheet.clear()
                worksheet.append_row(header)
                if rows:
                    worksheet.append_rows(rows)

                results[sheet_name] = True
                logger.info(f"Successfully updated {sheet_name} with {len(rows)} rows")

            except Exception as e:
                logger.error(f"Error updating {sheet_name}: {str(e)}")
                results[sheet_name] = False

        # Clear all caches after bulk update
        _enhanced_cache.clear()

        return results

    except Exception as e:
        logger.error(f"Error in bulk update: {str(e)}")
        # For any sheet not already processed, mark as failed
        for sheet_name in updates:
            if sheet_name not in results:
                results[sheet_name] = False
        return results


def get_stats_and_health() -> Dict[str, Any]:
    """
    Get connection statistics and health information.

    Returns:
        Dictionary with stats about API usage and cache health
    """
    return {
        "cache_size": len(_enhanced_cache),
        "last_cache_clear": _enhanced_cache._last_cleanup.isoformat(),
        "connections": {
            "sheets_api_calls": 0,  # Placeholder for tracking API calls
            "rate_limit_hits": 0  # Placeholder for tracking rate limits
        },
        "health": {
            "status": "healthy",
            "last_error": None
        },
        "version": "2.0.0"
    }


# This allows running the module directly for testing
if __name__ == "__main__":
    try:
        logging.basicConfig(level=logging.INFO)
        logger.info("Testing oauth_sheets_connector.py")

        # Basic test - attempt to get plants data
        if USE_MOCK_DATA:
            logger.info("Using mock data for testing")
            plants = get_plants_data()
            logger.info(f"Successfully retrieved {len(plants)} mock plants")
        else:
            logger.info("Attempting to connect to Google Sheets")
            try:
                client = get_sheets_client()
                logger.info("Successfully connected to Google Sheets")
                plants = get_plants_data()
                logger.info(f"Successfully retrieved {len(plants)} plants from Google Sheets")

                # Test the enhanced caching
                logger.info("Testing cache efficiency...")

                # First call - should be a cache miss
                start_time = time.time()
                plants1 = get_plants_data()
                first_call_time = time.time() - start_time

                # Second call - should be a cache hit
                start_time = time.time()
                plants2 = get_plants_data()
                second_call_time = time.time() - start_time

                logger.info(f"First call (cache miss): {first_call_time:.4f}s")
                logger.info(f"Second call (cache hit): {second_call_time:.4f}s")
                logger.info(f"Speed improvement: {(first_call_time / second_call_time):.1f}x faster")

                # Test batch retrieval
                logger.info("Testing batch data retrieval...")
                start_time = time.time()
                batch_plants, batch_products, batch_kits = get_all_data()
                batch_time = time.time() - start_time

                logger.info(f"Batch retrieval time: {batch_time:.4f}s")
                logger.info(
                    f"Retrieved {len(batch_plants)} plants, {len(batch_products)} products, {len(batch_kits)} kits")

                # Print cache stats
                logger.info(f"Cache statistics: {get_stats_and_health()}")

            except GoogleSheetsConnectionError as e:
                logger.error(f"Connection error: {str(e)}")
            except GoogleSheetsDataError as e:
                logger.error(f"Data error: {str(e)}")

    except Exception as e:
        logger.error(f"Error testing oauth_sheets_connector.py: {str(e)}")