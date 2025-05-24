# test_recommendation.py
import logging
import json
from core.recommendation_engine import get_recommendations
from typing import Dict, Any

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_recommendation')


def test_recommendation_engine():
    """Test the recommendation engine with various user preferences"""

    # Test case 1: Basic recommendation for a living room
    user_preferences_1 = {
        'location': 'living_room',
        'experience_level': 'beginner',
        'maintenance': 'low',
        'light': 'medium',
        'subscription_tier': 'free'
    }

    # Test case 2: Advanced user with specific light requirements
    user_preferences_2 = {
        'location': 'bathroom',
        'experience_level': 'advanced',
        'maintenance': 'high',
        'light': 'low',
        'humidity': 70,
        'subscription_tier': 'subscriber'
    }

    # Test case 3: Invalid preferences (missing location)
    user_preferences_3 = {
        'experience_level': 'intermediate',
        'maintenance': 'medium',
        'light': 'bright_indirect',
        'subscription_tier': 'free'
    }

    # Test case 4: Premium plants filtering
    user_preferences_4 = {
        'location': 'kitchen',
        'experience_level': 'beginner',
        'maintenance': 'low',
        'light': 'bright_indirect',
        'subscription_tier': 'subscriber'
    }

    # Run tests
    test_cases = [
        ('Basic living room', user_preferences_1),
        ('Advanced bathroom', user_preferences_2),
        ('Invalid preferences', user_preferences_3),
        ('Premium plants', user_preferences_4)
    ]

    for test_name, preferences in test_cases:
        logger.info(f"Running test: {test_name}")
        try:
            results = get_recommendations(preferences)

            # Print summarized results
            print(f"\n----- RESULTS FOR: {test_name} -----")
            print(f"Error: {results.get('error')}")
            print(f"Message: {results.get('message')}")

            if not results.get('error'):
                print(f"Plants found: {len(results.get('plants', []))}")
                if results.get('plants'):
                    print("Top 3 plants:")
                    for i, plant in enumerate(results.get('plants', [])[:3]):
                        print(f"  {i + 1}. {plant.get('name')} (Score: {plant.get('normalized_score')})")

                print(f"Products found: {len(results.get('products', []))}")
                print(f"Kits found: {len(results.get('kits', []))}")

                # Show analytics summary
                if 'analytics' in results and results['analytics'].get('available'):
                    print("\nAnalytics:")
                    print(f"  Difficulty breakdown: {results['analytics']['basic']['difficulty_breakdown']}")

                # Show subscription features
                print(f"\nSubscription tier: {results.get('subscription_tier')}")
                if 'subscriber_features' in results:
                    features = results['subscriber_features']
                    print(f"  Service fee: {features.get('service_fee_percentage')}%")
                    print(f"  Can save custom kits: {features.get('can_save_custom_kits')}")

            # Save full results to file for inspection
            filename = f"test_results_{test_name.replace(' ', '_').lower()}.json"
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"Full results saved to {filename}")

        except Exception as e:
            logger.error(f"Test failed: {str(e)}", exc_info=True)
            print(f"Test failed: {str(e)}")

        print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    test_recommendation_engine()