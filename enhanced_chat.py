# enhanced_chat.py
"""
Enhanced ChatGPT-like conversational AI for plant assistance
Now with real AWS DynamoDB data integration
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('enhanced_chat')

# Initialize OpenAI
openai_client = None
try:
    from openai import OpenAI

    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    logger.info("✅ OpenAI client initialized")
except Exception as e:
    logger.error(f"❌ OpenAI setup failed: {e}")

# Initialize AWS DynamoDB
dynamo_connector = None
try:
    from aws.dynamo_connector import DynamoConnector

    # Configure for your migrated tables
    dynamo_connector = DynamoConnector(
        region_name=os.getenv('AWS_REGION'),
        table_prefix='growvrd-'
    )


    # Override table names to match your migrated tables
    def get_full_table_name(table_type: str) -> str:
        table_map = {
            'plants': os.getenv('DYNAMODB_PLANTS_TABLE'),
            'products': os.getenv('DYNAMODB_PRODUCTS_TABLE'),
            'users': os.getenv('DYNAMODB_USERS_TABLE'),
            'kits': os.getenv('DYNAMODB_KITS_TABLE'),
            'plant_products': os.getenv('DYNAMODB_PLANT_PRODUCTS_TABLE'),
            'user_plants': os.getenv('DYNAMODB_USER_PLANTS_TABLE'),
            'local_vendors': os.getenv('DYNAMODB_LOCAL_VENDORS_TABLE')
        }
        return table_map.get(table_type, f"growvrd-{table_type}-development")


    dynamo_connector._get_table_name = get_full_table_name
    logger.info("✅ DynamoDB connector initialized with migrated data")

except Exception as e:
    logger.error(f"❌ DynamoDB setup failed: {e}")


def create_chatgpt_like_plant_expert_prompt() -> str:
    """Create an advanced system prompt that leverages your real data"""
    return """You are GrowVRD, an expert plant consultant with access to a comprehensive plant database and user collections. You're enthusiastic, knowledgeable, and genuinely care about helping people succeed with plants.

🌿 YOUR CAPABILITIES:
- Access to real plant database with detailed care instructions
- Knowledge of plant-product compatibility ratings (1-5 scale)
- Understanding of room conditions and plant placement
- Personal plant tracking by user nicknames
- Product recommendations with real Amazon links

💬 CONVERSATION STYLE:
- Natural, enthusiastic, and encouraging
- Ask follow-up questions to understand their needs
- Reference their existing plants when known
- Provide specific, actionable advice
- Use emojis appropriately for friendliness

🎯 YOUR EXPERTISE AREAS:
1. **Plant Recommendations**: Based on light, space, experience level
2. **Care Instructions**: Watering, lighting, fertilizing, troubleshooting
3. **Product Suggestions**: Pots, soil, tools with compatibility ratings
4. **Problem Diagnosis**: Help identify and solve plant issues
5. **Room Planning**: Best plants for specific spaces and conditions

📊 DATA-DRIVEN RESPONSES:
- When suggesting plants, mention specific care requirements
- Include compatibility warnings for products (ratings 1-2)
- Recommend highly compatible products (ratings 4-5)
- Reference room sensor data when available
- Provide realistic care schedules

🔄 CONVERSATION MANAGEMENT:
- Build on previous conversation context
- Remember user preferences and plants
- Ask clarifying questions when needed
- Offer to dive deeper into specific topics
- Always end with a helpful next step or question

IMPORTANT: Keep responses conversational and helpful. Don't mention technical details about databases or ratings unless relevant to the user's question."""


def get_user_context(user_data: Dict[str, Any]) -> str:
    """Build context about the user's existing plants and preferences"""
    context = ""

    if user_data.get('plants'):
        plant_names = [plant.get('nickname', plant.get('name', 'plant')) for plant in user_data['plants']]
        context += f"User has plants: {', '.join(plant_names)}. "

    if user_data.get('room_conditions'):
        rooms = list(user_data['room_conditions'].keys())
        context += f"User has room data for: {', '.join(rooms)}. "

    if user_data.get('experience_level'):
        context += f"Experience level: {user_data['experience_level']}. "

    return context


def get_plant_recommendations_with_data(preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get plant recommendations using real DynamoDB data"""
    if not dynamo_connector:
        return []

    try:
        # Get all plants from DynamoDB
        all_plants = dynamo_connector.get_plants()

        # Filter based on preferences
        filtered_plants = []
        for plant in all_plants:
            # Light filtering
            if preferences.get('light'):
                plant_light = plant.get('natural_sunlight_needs', '').lower()
                if preferences['light'] in plant_light:
                    filtered_plants.append(plant)
            else:
                filtered_plants.append(plant)

        # Sort by difficulty for beginners
        if preferences.get('experience') == 'beginner':
            filtered_plants.sort(key=lambda p: p.get('difficulty', 'medium') == 'easy', reverse=True)

        return filtered_plants[:5]  # Return top 5

    except Exception as e:
        logger.error(f"Error getting plant recommendations: {e}")
        return []


def get_compatible_products(plant_id: str) -> List[Dict[str, Any]]:
    """Get products compatible with a specific plant"""
    if not dynamo_connector:
        return []

    try:
        # Get plant-product relationships
        relationships = dynamo_connector.get_products_for_plant(plant_id)

        # Filter for high compatibility (rating 4-5)
        high_compat = [r for r in relationships if r.get('compatibility_rating', 0) >= 4]

        return high_compat[:3]  # Return top 3

    except Exception as e:
        logger.error(f"Error getting compatible products: {e}")
        return []


def enhanced_chat_response(message: str, conversation_history: List[Dict], user_context: Dict = None) -> Dict[str, Any]:
    """Generate enhanced ChatGPT-like response with real data integration"""

    if not openai_client:
        return {
            "type": "error",
            "content": "AI assistant is currently unavailable. Please try again later.",
            "suggestions": ["Tell me about snake plants", "What plants are good for beginners?"]
        }

    try:
        # Build system message
        system_prompt = create_chatgpt_like_plant_expert_prompt()

        # Add user context if available
        if user_context:
            context_info = get_user_context(user_context)
            system_prompt += f"\n\nUSER CONTEXT: {context_info}"

        # Prepare conversation for OpenAI
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 6 messages)
        recent_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        for msg in recent_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        # Add current message
        messages.append({"role": "user", "content": message})

        # Call OpenAI with optimized settings
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=600,
            temperature=0.8,  # More creative responses
            presence_penalty=0.1,
            frequency_penalty=0.1
        )

        ai_response = response.choices[0].message.content

        # Enhance response with real data if needed
        enhanced_response = enhance_response_with_data(ai_response, message)

        return {
            "type": "text",
            "content": enhanced_response,
            "data_enhanced": True,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Enhanced chat error: {e}")
        return {
            "type": "error",
            "content": "I'm having trouble processing that right now. Could you try rephrasing your question?",
            "fallback": True
        }


def enhance_response_with_data(ai_response: str, user_message: str) -> str:
    """Enhance AI response with real plant data when relevant"""

    # Check if user is asking for plant recommendations
    if any(keyword in user_message.lower() for keyword in ['recommend', 'suggest', 'what plant', 'best plant']):
        # Extract preferences from AI response or user message
        preferences = extract_preferences_from_text(user_message + " " + ai_response)

        if preferences:
            plant_recs = get_plant_recommendations_with_data(preferences)

            if plant_recs:
                ai_response += "\n\n🌱 **Based on our plant database, here are my top recommendations:**\n"
                for i, plant in enumerate(plant_recs[:3], 1):
                    name = plant.get('name', 'Unknown').replace('_', ' ').title()
                    care_level = plant.get('difficulty', 'moderate')
                    light = plant.get('natural_sunlight_needs', 'medium light')

                    ai_response += f"\n{i}. **{name}** - {care_level} care, needs {light}"

                    # Add care tip
                    if plant.get('watering_frequency'):
                        ai_response += f" • Water {plant['watering_frequency']}"

    # Check if user is asking about specific plant care
    elif any(keyword in user_message.lower() for keyword in ['care for', 'how to', 'watering', 'light']):
        # Could enhance with specific care data from DynamoDB
        pass

    return ai_response


def extract_preferences_from_text(text: str) -> Dict[str, Any]:
    """Extract plant preferences from natural language text"""
    text_lower = text.lower()
    preferences = {}

    # Location detection
    locations = {
        'bedroom': ['bedroom', 'bed room'],
        'kitchen': ['kitchen', 'cooking'],
        'living_room': ['living room', 'lounge'],
        'bathroom': ['bathroom', 'bath'],
        'office': ['office', 'desk', 'work']
    }

    for location, keywords in locations.items():
        if any(keyword in text_lower for keyword in keywords):
            preferences['location'] = location
            break

    # Light detection
    if any(term in text_lower for term in ['bright', 'sunny', 'lots of light']):
        preferences['light'] = 'bright'
    elif any(term in text_lower for term in ['low light', 'dark', 'shade']):
        preferences['light'] = 'low'
    elif any(term in text_lower for term in ['medium', 'some light']):
        preferences['light'] = 'medium'

    # Experience detection
    if any(term in text_lower for term in ['beginner', 'new to', 'first time']):
        preferences['experience'] = 'beginner'
    elif any(term in text_lower for term in ['experienced', 'expert', 'advanced']):
        preferences['experience'] = 'advanced'

    # Maintenance detection
    if any(term in text_lower for term in ['low maintenance', 'easy', 'simple']):
        preferences['maintenance'] = 'low'
    elif any(term in text_lower for term in ['high maintenance', 'challenging']):
        preferences['maintenance'] = 'high'

    return preferences


# Test function
def test_enhanced_chat():
    """Test the enhanced chat system"""
    print("🧪 Testing Enhanced Chat System")
    print("=" * 40)

    # Test messages
    test_messages = [
        "Hi! I'm new to plants and want something for my bedroom",
        "What's the best low-maintenance plant for a beginner?",
        "How do I care for a snake plant?",
        "My fiddle leaf fig leaves are turning yellow, help!"
    ]

    conversation_history = []

    for i, message in enumerate(test_messages, 1):
        print(f"\n{i}. User: {message}")

        response = enhanced_chat_response(message, conversation_history)
        print(f"   GrowVRD: {response.get('content', 'No response')[:200]}...")

        # Add to conversation history
        conversation_history.append({"role": "user", "content": message})
        conversation_history.append({"role": "assistant", "content": response.get('content', '')})

    print("\n✅ Enhanced chat test complete!")


if __name__ == "__main__":
    test_enhanced_chat()