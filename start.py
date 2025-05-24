import os
import logging
from app import app
from core.mock_data import get_mock_plants, get_mock_products, get_mock_kits

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('start')

# Check if data files exist, if not create them
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Preload mock data to confirm functionality
try:
    plants = get_mock_plants()
    products = get_mock_products()
    kits = get_mock_kits()
    logger.info(f"Preloaded mock data: {len(plants)} plants, {len(products)} products, {len(kits)} kits")
except Exception as e:
    logger.error(f"Error preloading mock data: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting GrowVRD application on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)