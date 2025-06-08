import os
from dotenv import load_dotenv
import logging

# Load environment variables from .env file if it exists
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('config')


class Config:
    """Configuration settings for GrowVRD"""

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = ENVIRONMENT == "development"

    # Google Sheets
    SHEETS_TOKEN_PATH = os.getenv("GROWVRD_TOKEN_PATH", "token.pickle")
    CREDENTIALS_PATH = os.getenv("GROWVRD_CREDENTIALS_PATH", "client_secrets.json")

    # Sheet names
    PLANTS_SHEET = "GrowVRD_Plants"
    PRODUCTS_SHEET = "GrowVRD_Products"
    KITS_SHEET = "GrowVRD_Kits"
    USERS_SHEET = "GrowVRD_Users"
    PLANT_PRODUCTS_SHEET = "GrowVRD_PlantProducts"
    USER_PLANTS_SHEET = "GrowVRD_UserPlants"

    # Rate limiting
    FREE_TIER_DAILY_LIMIT = int(os.getenv("FREE_TIER_DAILY_LIMIT", "10"))
    SUBSCRIBER_TIER_DAILY_LIMIT = int(os.getenv("SUBSCRIBER_TIER_DAILY_LIMIT", "50"))

    # Cache settings
    CACHE_TIMEOUT = int(os.getenv("CACHE_TIMEOUT", "300"))

    # Service fees
    FREE_TIER_FEE = float(os.getenv("FREE_TIER_FEE", "0.10"))
    SUBSCRIBER_TIER_FEE = float(os.getenv("SUBSCRIBER_TIER_FEE", "0.03"))

    @classmethod
    def validate(cls):
        """Validate that critical configuration is present"""
        missing = []

        # Add checks for critical config values
        if not os.path.exists(cls.CREDENTIALS_PATH):
            logger.warning(f"Credentials file not found at: {cls.CREDENTIALS_PATH}")
            missing.append("CREDENTIALS_PATH")

        return len(missing) == 0, missing


# Create a global config instance
config = Config()

# Validate configuration on import
is_valid, missing_config = config.validate()
if not is_valid:
    logger.warning(f"Configuration is missing these critical items: {missing_config}")


class Config:
    # ... existing config ...

    # AWS Configuration - ADD THESE LINES
    USE_DYNAMODB = True  # Switch to DynamoDB
    FALLBACK_TO_SHEETS = True  # Safety fallback during transition

    # AWS Settings
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET')

    # DynamoDB Tables
    DYNAMODB_PLANTS_TABLE = os.getenv('DYNAMODB_PLANTS_TABLE')
    DYNAMODB_PRODUCTS_TABLE = os.getenv('DYNAMODB_PRODUCTS_TABLE')
    DYNAMODB_KITS_TABLE = os.getenv('DYNAMODB_KITS_TABLE')
    DYNAMODB_USERS_TABLE = os.getenv('DYNAMODB_USERS_TABLE')
    DYNAMODB_PLANT_PRODUCTS_TABLE = os.getenv('DYNAMODB_PLANT_PRODUCTS_TABLE')
    DYNAMODB_USER_PLANTS_TABLE = os.getenv('DYNAMODB_USER_PLANTS_TABLE')
    DYNAMODB_LOCAL_VENDORS_TABLE = os.getenv('DYNAMODB_LOCAL_VENDORS_TABLE')

    # Cognito
    COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
    COGNITO_CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')