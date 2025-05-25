"""
GrowVRD - Enhanced Chat-based Plant Recommendation System
Main Flask Application with Fixed OpenAI Integration
"""
import os
import json
import logging
import uuid
import time
import re
from flask import Flask, request, jsonify, send_from_directory
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('app')

# Initialize OpenAI client - FIXED VERSION
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    logger.warning("OPENAI_API_KEY environment variable not set. OpenAI functionality will not work.")
    openai_client = None
else:
    try:
        # Use the new OpenAI client format
        from openai import OpenAI

        openai_client = OpenAI(api_key=openai_api_key)
        logger.info("OpenAI client initialized successfully")
    except ImportError:
        logger.error("OpenAI library not installed. Run: pip install openai>=1.0.0")
        openai_client = None
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {str(e)}")
        openai_client = None

# Environment configuration
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
USE_MOCK_DATA = os.environ.get("USE_MOCK_DATA", "true").lower() == "true"
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Import core modules
try:
    from core.mock_data import get_mock_plants, get_mock_products, get_mock_kits
    from core.filters import filter_plants, filter_by_location, filter_by_difficulty, filter_by_maintenance, \
        filter_by_light_requirements

    logger.info("Successfully imported core modules")
except ImportError as e:
    logger.error(f"Failed to import core modules: {str(e)}")


    # Define mock functions if imports fail
    def get_mock_plants():
        return []


    def get_mock_products():
        return []


    def get_mock_kits():
        return []


    def filter_plants(plants, criteria):
        return plants

# Import Perenual API integration
PERENUAL_ENABLED = False
try:
    from api.perenual_api import search_species, get_species_details, PerenualAPIError
    from api.perenual_integration import search_and_import_plants, find_and_import_plants_for_environment

    logger.info("Successfully imported Perenual API integration")
    PERENUAL_ENABLED = True
except ImportError as e:
    logger.error(f"Failed to import Perenual API integration: {str(e)}")
    PERENUAL_ENABLED = False

# Create Flask app
app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# In-memory conversation storage
conversations = {}

# In-memory cache for Perenual data
perenual_cache = {}
CACHE_EXPIRY = int(os.environ.get("CACHE_TIMEOUT", "3600"))  # 1 hour


class ConversationStage:
    """Enum-like class for conversation stages"""
    GREETING = "greeting"
    LOCATION_DISCOVERY = "location_discovery"
    LIGHT_DISCOVERY = "light_discovery"
    EXPERIENCE_DISCOVERY = "experience_discovery"
    MAINTENANCE_DISCOVERY = "maintenance_discovery"
    PREFERENCE_REFINEMENT = "preference_refinement"
    RECOMMENDATION_READY = "recommendation_ready"
    FOLLOW_UP = "follow_up"
    CARE_DISCUSSION = "care_discussion"


def create_plant_expert_system_prompt():
    """Create a comprehensive system prompt for plant expertise"""
    return """You are GrowVRD, the world's most knowledgeable and friendly plant care assistant. You help people find perfect plants for their spaces through natural conversation.

CORE PERSONALITY:
- Friendly, encouraging, and genuinely excited about plants
- Ask thoughtful follow-up questions to understand their space better
- Remember everything from our conversation and build on it
- Explain plant recommendations clearly with specific reasons
- Share care tips and troubleshooting advice naturally

CONVERSATION UNDERSTANDING:
- You understand natural language like "it's for my bedroom" or "something low maintenance"
- You can extract multiple pieces of information from a single message
- You maintain context across the entire conversation
- You ask clarifying questions when needed, but don't repeat what you already know

INFORMATION TO GATHER:
1. WHERE they want plants (specific room/location)
2. LIGHTING conditions in that space
3. Their EXPERIENCE level and comfort with plant care
4. How much MAINTENANCE/attention they want to give
5. Any SPECIFIC preferences (plant types, functions, constraints)

RESPONSE RULES:
- Always acknowledge what they've told you
- Ask ONE follow-up question to get the most important missing information
- Be conversational and natural, not like a form
- When you have enough info (location + 1-2 other preferences), provide plant recommendations
- For follow-up questions about plants, give detailed care advice

At the end of EVERY response, include a JSON object with extracted preferences:

```json
{
  "location": "bedroom",
  "light": "low", 
  "experience_level": "beginner",
  "maintenance": "low",
  "plant_types": ["air purifying"],
  "conversation_stage": "recommendation_ready",
  "confidence": 0.9
}
```

CONVERSATION STAGES:
- greeting: Initial hello
- location_discovery: Finding out where they want plants
- light_discovery: Understanding lighting conditions
- experience_discovery: Learning about experience
- maintenance_discovery: Understanding care preferences
- recommendation_ready: Have enough info to recommend plants
- follow_up: User asking about recommended plants

Remember: Understand natural language and maintain conversation context!"""


def call_openai_safely(messages: List[Dict], max_tokens: int = 600, temperature: float = 0.4) -> Optional[str]:
    """Safely call OpenAI API with proper error handling"""
    if not openai_client:
        logger.warning("OpenAI client not available")
        return None

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )

        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            logger.error("No choices in OpenAI response")
            return None

    except Exception as e:
        logger.error(f"OpenAI API call failed: {str(e)}")
        return None


def extract_json_from_response(response_text: str) -> Tuple[Dict, str]:
    """Extract JSON preferences from OpenAI response"""
    preferences = {}
    clean_text = response_text

    try:
        # Look for JSON in the response
        json_start = response_text.find('```json')
        if json_start != -1:
            json_start = response_text.find('{', json_start)
            json_end = response_text.find('```', json_start)
            if json_end == -1:
                json_end = len(response_text)
            json_str = response_text[json_start:json_end]
        else:
            # Look for JSON without markdown
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_str = response_text[json_start:json_end]

        if json_start != -1 and json_end > json_start:
            preferences = json.loads(json_str)
            # Remove JSON from natural response
            clean_text = response_text[:json_start].strip()
            if not clean_text:
                clean_text = response_text[json_end:].strip()

    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"No valid JSON found in OpenAI response: {e}")

    return preferences, clean_text


def process_with_openai(message: str, conversation_history: List[Dict], current_preferences: Dict) -> Tuple[
    Dict[str, Any], str]:
    """Process message with OpenAI - FIXED VERSION"""

    # Build conversation context
    system_prompt = create_plant_expert_system_prompt()

    # Create messages for OpenAI
    messages = [{"role": "system", "content": system_prompt}]

    # Add recent conversation history
    if conversation_history:
        # Add last 6 messages for context
        recent_history = conversation_history[-6:]
        messages.extend(recent_history)

    # Add current message with context
    context_message = f"""Current known preferences: {json.dumps(current_preferences)}

User just said: "{message}"

Based on our conversation so far, respond naturally and include the JSON preferences at the end."""

    messages.append({"role": "user", "content": context_message})

    # Call OpenAI
    response_text = call_openai_safely(messages)

    if response_text:
        # Extract preferences and clean text
        preferences, clean_response = extract_json_from_response(response_text)
        return preferences, clean_response
    else:
        # Fallback when OpenAI fails
        logger.warning("OpenAI call failed, using fallback processing")
        return extract_preferences_fallback(message, current_preferences)


def extract_preferences_fallback(message: str, current_preferences: Dict) -> Tuple[Dict, str]:
    """Fallback preference extraction when OpenAI is unavailable"""
    message_lower = message.lower()
    new_prefs = {}

    # Location detection
    location_keywords = {
        'bedroom': ['bedroom', 'bed room'],
        'kitchen': ['kitchen', 'cooking', 'herb'],
        'living_room': ['living room', 'living', 'lounge'],
        'bathroom': ['bathroom', 'bath'],
        'office': ['office', 'desk', 'work'],
        'balcony': ['balcony', 'outdoor', 'patio']
    }

    for location, keywords in location_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            new_prefs['location'] = location
            break

    # Light detection
    if any(word in message_lower for word in ['bright', 'sunny', 'sun']):
        new_prefs['light'] = 'bright_indirect'
    elif any(word in message_lower for word in ['dark', 'shade', 'low light']):
        new_prefs['light'] = 'low'
    elif any(word in message_lower for word in ['medium', 'moderate']):
        new_prefs['light'] = 'medium'

    # Experience detection
    if any(word in message_lower for word in ['beginner', 'new', 'first time']):
        new_prefs['experience_level'] = 'beginner'
    elif any(word in message_lower for word in ['experienced', 'advanced']):
        new_prefs['experience_level'] = 'advanced'

    # Maintenance detection
    if any(word in message_lower for word in ['low maintenance', 'easy', 'simple']):
        new_prefs['maintenance'] = 'low'
    elif any(word in message_lower for word in ['high maintenance']):
        new_prefs['maintenance'] = 'high'

    # Generate response
    if not current_preferences.get('location') and not new_prefs.get('location'):
        response = "I'd love to help you find the perfect plants! Which room are you thinking about?"
    elif not current_preferences.get('light') and not new_prefs.get('light'):
        response = f"Great! For your {new_prefs.get('location', 'space')}, how much light does it get?"
    else:
        response = "Perfect! Let me find some great plants for you based on what you've told me."

    return new_prefs, response


def should_provide_recommendations(preferences: Dict, message_count: int) -> bool:
    """Determine if we should provide plant recommendations"""

    # Minimum requirements: location + one other preference
    has_location = 'location' in preferences and preferences['location']
    has_other_prefs = any(key in preferences and preferences[key] for key in
                          ['light', 'experience_level', 'maintenance', 'plant_types'])

    # Provide recommendations if we have minimum info
    if has_location and has_other_prefs:
        return True

    # If conversation is getting long, provide recommendations with caveats
    if message_count > 6 and has_location:
        return True

    return False


def get_cached_perenual_plants(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached plants if they exist and are not expired"""
    if cache_key in perenual_cache:
        timestamp, plants = perenual_cache[cache_key]
        if time.time() - timestamp < CACHE_EXPIRY:
            return plants
    return None


def cache_perenual_plants(cache_key: str, plants: List[Dict[str, Any]]) -> None:
    """Cache plants with current timestamp"""
    perenual_cache[cache_key] = (time.time(), plants)


def get_plants_from_perenual(preferences: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """Get plants from Perenual API based on user preferences"""
    if not PERENUAL_ENABLED:
        return []

    try:
        location = preferences.get('location')
        light = preferences.get('light')
        maintenance = preferences.get('maintenance')
        plant_types = preferences.get('plant_types', [])

        # Create cache key
        cache_key = f"l:{location or 'any'}_lt:{light or 'any'}_m:{maintenance or 'any'}_pt:{','.join(plant_types)}"

        # Check cache
        cached_plants = get_cached_perenual_plants(cache_key)
        if cached_plants:
            logger.info(f"Using cached Perenual plants for {cache_key}")
            return cached_plants

        plants = []

        # Strategy 1: Environment-based search
        if location and light:
            plants = find_and_import_plants_for_environment(
                location=location,
                light_level=light,
                maintenance_level=maintenance,
                limit=limit
            )

        # Strategy 2: Plant type search
        if not plants and plant_types:
            for plant_type in plant_types[:2]:
                type_plants = search_and_import_plants(
                    query=plant_type,
                    limit=limit // len(plant_types[:2]),
                    save_to_database=False
                )
                plants.extend(type_plants)

        # Strategy 3: Location-based search
        if not plants and location:
            location_terms = {
                "kitchen": "herb culinary",
                "living_room": "houseplant decorative",
                "bedroom": "air purifying calming",
                "bathroom": "humidity tolerant",
                "office": "low light desk plant",
                "balcony": "outdoor container"
            }
            search_term = location_terms.get(location, "indoor plant")
            plants = search_and_import_plants(
                query=search_term,
                limit=limit,
                save_to_database=False
            )

        if plants:
            cache_perenual_plants(cache_key, plants)
            logger.info(f"Found {len(plants)} plants from Perenual")

        return plants

    except Exception as e:
        logger.error(f"Error getting plants from Perenual: {str(e)}")
        return []


def apply_smart_filters(plants_data: List[Dict[str, Any]], preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply filters progressively to avoid over-filtering"""
    if not plants_data:
        return []

    current_plants = plants_data.copy()
    filter_criteria = {}

    # Apply filters one by one, checking that we still have results
    filters_to_try = [
        ('location', preferences.get('location')),
        ('light', preferences.get('light')),
        ('experience_level', preferences.get('experience_level')),
        ('maintenance', preferences.get('maintenance'))
    ]

    for filter_name, filter_value in filters_to_try:
        if not filter_value:
            continue

        # Test if this filter would leave us with plants
        test_criteria = filter_criteria.copy()
        test_criteria[filter_name] = filter_value

        test_plants = filter_plants(plants_data, test_criteria)

        if test_plants:  # If we still have plants, apply this filter
            filter_criteria[filter_name] = filter_value
            current_plants = test_plants
            logger.info(f"Applied filter {filter_name}={filter_value}: {len(current_plants)} plants remain")
        else:
            logger.info(f"Skipping filter {filter_name}={filter_value}: would eliminate all plants")

    return current_plants


def process_chat_message(message: str, session_id: str) -> Dict[str, Any]:
    """Process chat message - FIXED VERSION"""
    try:
        # Get or initialize conversation
        if session_id not in conversations:
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0
            }

        conversation = conversations[session_id]
        conversation['message_count'] += 1

        # Handle reset commands
        message_lower = message.lower()
        if any(cmd in message_lower for cmd in ["restart", "reset", "start over", "new conversation"]):
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0
            }
            return {
                'type': 'text',
                'content': "Let's start fresh! I'm here to help you find the perfect plants for your space. What kind of plants are you looking for? 🌿",
                'preferences': {}
            }

        # Add user message to history
        conversation['messages'].append({"role": "user", "content": message})

        # Process with OpenAI (or fallback)
        try:
            new_preferences, ai_response = process_with_openai(
                message,
                conversation['messages'][:-1],  # Don't include current message
                conversation['preferences']
            )
        except Exception as e:
            logger.error(f"Error processing with OpenAI: {str(e)}")
            new_preferences, ai_response = extract_preferences_fallback(message, conversation['preferences'])

        # Update stored preferences
        for key, value in new_preferences.items():
            if value and key not in ['confidence', 'conversation_stage']:
                if key in ['plant_types'] and isinstance(value, list):
                    # Merge arrays
                    if key not in conversation['preferences']:
                        conversation['preferences'][key] = []
                    for item in value:
                        if item and item not in conversation['preferences'][key]:
                            conversation['preferences'][key].append(item)
                else:
                    conversation['preferences'][key] = value

        logger.info(f"Session {session_id}: Updated preferences={conversation['preferences']}")

        # Check if we should provide recommendations
        should_recommend = should_provide_recommendations(
            conversation['preferences'],
            conversation['message_count']
        )

        if should_recommend:
            # Get plant recommendations
            plants_data = []

            # Try Perenual first
            if PERENUAL_ENABLED:
                plants_data = get_plants_from_perenual(conversation['preferences'])

            # Fall back to mock data with smart filtering
            if not plants_data:
                mock_plants = get_mock_plants()
                plants_data = apply_smart_filters(mock_plants, conversation['preferences'])

            if plants_data:
                # Limit to top 3 for chat interface
                top_plants = plants_data[:3]

                # Use AI response or generate one
                if not ai_response or len(ai_response.strip()) < 20:
                    location_display = conversation['preferences'].get('location', 'space').replace('_', ' ')
                    plant_names = [plant.get('name', '').replace('_', ' ').title() for plant in top_plants]
                    ai_response = f"Perfect! For your {location_display}, I'd recommend: {', '.join(plant_names)}. These plants are great matches for your preferences!"

                # Always add a follow-up question
                if not any(q in ai_response.lower() for q in ['?', 'question', 'tell me', 'what do you']):
                    ai_response += " What questions do you have about caring for these plants?"

                conversation['messages'].append({"role": "assistant", "content": ai_response})

                return {
                    'type': 'recommendation',
                    'content': ai_response,
                    'data': {
                        'plants': top_plants,
                        'preferences': conversation['preferences']
                    },
                    'preferences': conversation['preferences']
                }
            else:
                # No plants found - ask for more info
                fallback_response = ai_response or "I'd love to help you find the perfect plants! To give you the best recommendations, could you tell me which room you're thinking about and what the lighting is like?"

                conversation['messages'].append({"role": "assistant", "content": fallback_response})

                return {
                    'type': 'text',
                    'content': fallback_response,
                    'preferences': conversation['preferences']
                }
        else:
            # Need more information - use AI response
            response_text = ai_response or "Tell me more about what you're looking for! Which room are you thinking about?"

            conversation['messages'].append({"role": "assistant", "content": response_text})

            return {
                'type': 'text',
                'content': response_text,
                'preferences': conversation['preferences']
            }

    except Exception as e:
        logger.error(f"Error in process_chat_message: {str(e)}", exc_info=True)
        return {
            'type': 'error',
            'content': "I'm sorry, I encountered an error. Could you try rephrasing your message?",
            'preferences': conversations.get(session_id, {}).get('preferences', {})
        }


# Routes
@app.route('/')
def home():
    """Serve the chat interface as the home page"""
    return send_from_directory('static', 'chat.html')


@app.route('/chat')
def chat_interface():
    """Serve the chat interface page"""
    return send_from_directory('static', 'chat.html')


@app.route('/form')
def form_interface():
    """Serve the original form interface"""
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)


@app.route('/api/chat', methods=['POST'])
def chat():
    """API endpoint for chat interactions - FIXED VERSION"""
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '')
        session_id = data.get('session_id', str(uuid.uuid4()))

        if not message.strip():
            return jsonify({
                "type": "error",
                "content": "Please enter a message",
                "session_id": session_id
            })

        logger.info(f"Processing message: '{message}' for session {session_id[:8]}...")

        # Process the message
        response = process_chat_message(message, session_id)
        response['session_id'] = session_id

        logger.info(f"Response type: {response.get('type')}, content length: {len(response.get('content', ''))}")

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": "I encountered an error processing your message. Please try again.",
            "session_id": data.get('session_id', str(uuid.uuid4()))
        })


@app.route('/api/debug', methods=['GET'])
def debug():
    """Debug endpoint to check system state"""
    debug_info = {
        "conversations_count": len(conversations),
        "openai_enabled": bool(openai_client),
        "perenual_enabled": PERENUAL_ENABLED,
        "environment": ENVIRONMENT,
        "cache_size": len(perenual_cache),
        "sample_conversations": [
            {
                "session_id": sid[:8] + "...",
                "message_count": conv.get('message_count', 0),
                "preferences": conv.get('preferences', {})
            }
            for sid, conv in list(conversations.items())[:3]
        ]
    }

    return jsonify(debug_info)


@app.route('/api/test-openai', methods=['POST'])
def test_openai():
    """Test OpenAI integration directly"""
    try:
        data = request.get_json() or {}
        test_message = data.get('message', 'I want plants for my bedroom')

        if not openai_client:
            return jsonify({
                "error": "OpenAI client not available",
                "api_key_set": bool(openai_api_key)
            })

        # Test simple OpenAI call
        messages = [
            {"role": "system",
             "content": "You are a helpful plant expert. Respond naturally and include JSON with preferences."},
            {"role": "user", "content": f"User said: {test_message}. Extract their preferences and respond naturally."}
        ]

        response_text = call_openai_safely(messages)

        if response_text:
            preferences, clean_text = extract_json_from_response(response_text)
            return jsonify({
                "success": True,
                "raw_response": response_text,
                "extracted_preferences": preferences,
                "clean_response": clean_text
            })
        else:
            return jsonify({
                "success": False,
                "error": "OpenAI call returned no response"
            })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.2.0",
        "openai_ready": bool(openai_client),
        "perenual_ready": PERENUAL_ENABLED,
        "features": ["fixed_openai_integration", "conversation_flow", "better_error_handling"]
    })


# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    host = '0.0.0.0'
    debug = ENVIRONMENT == 'development'

    logger.info(f"Starting GrowVRD v2.2 (FIXED) on {host}:{port}")
    logger.info(f"OpenAI client ready: {bool(openai_client)}")
    logger.info(f"Perenual enabled: {PERENUAL_ENABLED}")
    logger.info("🔧 FIXES: OpenAI client initialization, better error handling, improved conversation flow")

    app.run(debug=debug, host=host, port=port)