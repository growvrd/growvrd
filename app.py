"""
GrowVRD - Natural Conversational Plant Assistant
Enhanced with truly conversational AI and intelligent context management
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

# Initialize OpenAI client
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    logger.warning("OPENAI_API_KEY environment variable not set.")
    openai_client = None
else:
    try:
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
    from core.filters import filter_plants

    logger.info("Successfully imported core modules")
except ImportError as e:
    logger.error(f"Failed to import core modules: {str(e)}")


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
plant_cache = {}
CACHE_EXPIRY = 3600  # 1 hour


def create_advanced_plant_expert_prompt():
    """Create an advanced conversational plant expert system prompt"""
    return """You are GrowVRD, an expert plant consultant with 20+ years of experience helping people create thriving indoor gardens. You have an enthusiastic, warm personality and genuinely love helping people succeed with plants.

CONVERSATION STYLE:
- Be naturally conversational, like talking to a knowledgeable friend
- Show genuine excitement about plants and their benefits
- Ask follow-up questions that show you're really listening
- Remember and reference what they've already told you
- Use their name or personal details they've shared
- Be encouraging and supportive, especially for beginners
- Share interesting plant facts and care tips naturally in conversation

UNDERSTANDING CONTEXT:
- You perfectly understand natural language like "something for my bedroom" or "low maintenance stuff"
- When someone says "it's for my bedroom," you know they want plants FOR their bedroom
- You can extract multiple pieces of information from casual conversation
- You build on previous conversation context naturally
- You ask smart follow-up questions based on what you already know

INFORMATION GATHERING (gather naturally through conversation):
1. LOCATION: Where they want plants (bedroom, kitchen, living room, etc.)
2. LIGHTING: How much natural light the space gets
3. EXPERIENCE: Their comfort level with plant care
4. COMMITMENT: How much time/effort they want to spend
5. PREFERENCES: Specific needs (air purifying, pet-safe, flowering, etc.)
6. CONSTRAINTS: Budget, space, allergies, pets, etc.

RESPONSE GUIDELINES:
- Always acknowledge what they just told you
- Build on their previous messages naturally
- Ask ONE thoughtful follow-up question (not a list)
- When you have enough info (location + 2-3 other details), offer specific plant recommendations
- For plant care questions, give detailed, helpful advice
- Be encouraging and share why certain plants are great choices

PLANT RECOMMENDATIONS:
- When recommending, explain WHY each plant is perfect for them
- Mention specific benefits (air purifying, easy care, beautiful, etc.)
- Give a brief care overview that matches their commitment level
- Ask if they want to know more about any specific plant

ALWAYS end your response with this JSON (but don't mention it):
```json
{
  "location": "bedroom",
  "light": "medium", 
  "experience": "beginner",
  "maintenance": "low",
  "specific_needs": ["air purifying", "pet safe"],
  "ready_for_recommendations": true,
  "conversation_tone": "enthusiastic"
}
```

Remember: You're having a natural conversation with someone who's excited about plants. Be the knowledgeable, encouraging friend they need!"""


def call_openai_conversational(messages: List[Dict], max_tokens: int = 800, temperature: float = 0.7) -> Optional[str]:
    """Call OpenAI with settings optimized for natural conversation"""
    if not openai_client:
        logger.warning("OpenAI client not available")
        return None

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,  # Higher temperature for more natural responses
            presence_penalty=0.1,  # Slight penalty to avoid repetition
            frequency_penalty=0.1  # Encourage variety in responses
        )

        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            logger.error("No choices in OpenAI response")
            return None

    except Exception as e:
        logger.error(f"OpenAI API call failed: {str(e)}")
        return None


def extract_preferences_and_clean_response(response_text: str) -> Tuple[Dict, str]:
    """Extract JSON preferences and return clean conversational response"""
    preferences = {}
    clean_text = response_text

    try:
        # Look for JSON block
        json_pattern = r'```json\s*(\{.*?\})\s*```'
        json_match = re.search(json_pattern, response_text, re.DOTALL)

        if json_match:
            json_str = json_match.group(1)
            preferences = json.loads(json_str)
            # Remove JSON block from response
            clean_text = re.sub(json_pattern, '', response_text, flags=re.DOTALL).strip()
        else:
            # Look for bare JSON
            json_start = response_text.rfind('{')
            json_end = response_text.rfind('}') + 1

            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                try:
                    preferences = json.loads(json_str)
                    clean_text = response_text[:json_start].strip()
                except json.JSONDecodeError:
                    pass

    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"Could not extract JSON from response: {e}")

    return preferences, clean_text


def build_conversation_context(conversation_history: List[Dict], current_preferences: Dict, user_message: str) -> str:
    """Build rich context for OpenAI including conversation history and current state"""

    # Build a summary of what we know
    known_info = []
    if current_preferences.get('location'):
        known_info.append(f"wants plants for their {current_preferences['location']}")
    if current_preferences.get('light'):
        known_info.append(f"has {current_preferences['light']} light")
    if current_preferences.get('experience'):
        known_info.append(f"is a {current_preferences['experience']} with plants")
    if current_preferences.get('maintenance'):
        known_info.append(f"wants {current_preferences['maintenance']} maintenance")
    if current_preferences.get('specific_needs'):
        known_info.append(f"needs: {', '.join(current_preferences['specific_needs'])}")

    context = f"""CONVERSATION CONTEXT:
What we know so far: {' | '.join(known_info) if known_info else 'Just starting conversation'}

RECENT CONVERSATION:
"""

    # Add last few messages for context
    recent_messages = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
    for msg in recent_messages:
        role = "User" if msg['role'] == 'user' else "You"
        context += f"{role}: {msg['content']}\n"

    context += f"\nUser just said: \"{user_message}\"\n"
    context += f"\nRespond naturally as GrowVRD, building on what you know and what they just said."

    return context


def process_message_with_ai(message: str, conversation_history: List[Dict], current_preferences: Dict) -> Tuple[
    Dict, str]:
    """Process message with advanced OpenAI conversation handling"""

    # Create system message
    system_prompt = create_advanced_plant_expert_prompt()

    # Build conversation context
    context = build_conversation_context(conversation_history, current_preferences, message)

    # Create messages array
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context}
    ]

    # Call OpenAI
    response_text = call_openai_conversational(messages)

    if response_text:
        preferences, clean_response = extract_preferences_and_clean_response(response_text)
        logger.info(f"AI extracted preferences: {preferences}")
        return preferences, clean_response
    else:
        # Fallback for when OpenAI is unavailable
        return handle_message_fallback(message, current_preferences)


def handle_message_fallback(message: str, current_preferences: Dict) -> Tuple[Dict, str]:
    """Enhanced fallback processing when OpenAI is unavailable"""
    message_lower = message.lower()
    new_prefs = {}

    # Smart location detection
    location_patterns = {
        'bedroom': ['bedroom', 'bed room', 'sleeping', 'where i sleep'],
        'kitchen': ['kitchen', 'cooking area', 'where i cook', 'herb garden'],
        'living_room': ['living room', 'living', 'lounge', 'main room', 'family room'],
        'bathroom': ['bathroom', 'bath', 'shower room'],
        'office': ['office', 'desk', 'work space', 'study', 'home office'],
        'balcony': ['balcony', 'patio', 'deck', 'outside', 'outdoor']
    }

    for location, patterns in location_patterns.items():
        if any(pattern in message_lower for pattern in patterns):
            new_prefs['location'] = location
            break

    # Light detection
    if any(term in message_lower for term in ['bright', 'sunny', 'lots of light', 'very light']):
        new_prefs['light'] = 'bright'
    elif any(term in message_lower for term in ['dark', 'low light', 'not much light', 'shady']):
        new_prefs['light'] = 'low'
    elif any(term in message_lower for term in ['some light', 'medium', 'moderate']):
        new_prefs['light'] = 'medium'

    # Experience detection
    if any(term in message_lower for term in ['beginner', 'new', 'first time', 'never had', 'kill plants']):
        new_prefs['experience'] = 'beginner'
    elif any(term in message_lower for term in ['experienced', 'good with', 'lots of plants']):
        new_prefs['experience'] = 'experienced'

    # Maintenance preferences
    if any(term in message_lower for term in ['low maintenance', 'easy', 'simple', 'hands off', 'lazy']):
        new_prefs['maintenance'] = 'low'
    elif any(term in message_lower for term in ['high maintenance', 'lots of care', 'attentive']):
        new_prefs['maintenance'] = 'high'

    # Specific needs
    needs = []
    if any(term in message_lower for term in ['air purify', 'clean air', 'air quality']):
        needs.append('air purifying')
    if any(term in message_lower for term in ['pet safe', 'cat safe', 'dog safe', 'non toxic']):
        needs.append('pet safe')
    if any(term in message_lower for term in ['flower', 'bloom', 'colorful']):
        needs.append('flowering')
    if needs:
        new_prefs['specific_needs'] = needs

    # Generate contextual response
    if not current_preferences.get('location') and not new_prefs.get('location'):
        response = "I'd love to help you find some amazing plants! Which room are you thinking about adding some green friends to?"
    elif new_prefs.get('location') and not current_preferences.get('light'):
        room = new_prefs['location'].replace('_', ' ')
        response = f"Perfect! I love helping people green up their {room}! How much natural light does it typically get - bright and sunny, or more on the dim side?"
    elif current_preferences.get('location') and not current_preferences.get('experience'):
        response = "Great! Before I suggest the perfect plants, are you pretty new to plant parenting, or do you have some experience keeping plants happy?"
    else:
        response = "Awesome! I think I have some perfect plant suggestions for you. Let me find some amazing options!"
        new_prefs['ready_for_recommendations'] = True

    return new_prefs, response


def should_recommend_plants(preferences: Dict, message_count: int) -> bool:
    """Determine if we have enough info to make good recommendations"""
    has_location = preferences.get('location')
    has_light_or_experience = preferences.get('light') or preferences.get('experience')
    explicitly_ready = preferences.get('ready_for_recommendations')

    # Ready if we have location + one other preference, or if AI says we're ready
    return explicitly_ready or (has_location and has_light_or_experience) or message_count > 5


def get_smart_plant_recommendations(preferences: Dict, limit: int = 3) -> List[Dict[str, Any]]:
    """Get intelligent plant recommendations based on preferences"""
    plants = []

    # Try Perenual API first
    if PERENUAL_ENABLED and preferences.get('location'):
        try:
            plants = find_and_import_plants_for_environment(
                location=preferences.get('location'),
                light_level=preferences.get('light', 'medium'),
                maintenance_level=preferences.get('maintenance', 'low'),
                limit=limit
            )
        except Exception as e:
            logger.warning(f"Perenual API failed: {e}")

    # Fallback to mock data with smart filtering
    if not plants:
        mock_plants = get_mock_plants()

        # Apply progressive filtering
        filter_criteria = {}
        if preferences.get('location'):
            filter_criteria['location'] = preferences['location']
        if preferences.get('light'):
            filter_criteria['light'] = preferences['light']
        if preferences.get('experience'):
            filter_criteria['experience_level'] = preferences['experience']
        if preferences.get('maintenance'):
            filter_criteria['maintenance'] = preferences['maintenance']

        plants = filter_plants(mock_plants, filter_criteria)

    return plants[:limit]


def create_recommendation_response(plants: List[Dict], preferences: Dict, ai_response: str) -> str:
    """Create an engaging recommendation response"""
    if not plants:
        return ai_response or "I'm having trouble finding plants that match your exact needs. Could you tell me a bit more about your space or what you're looking for?"

    location = preferences.get('location', 'space').replace('_', ' ')

    if ai_response and len(ai_response.strip()) > 30:
        # Use AI response if it's substantial
        return ai_response
    else:
        # Generate enthusiastic recommendation
        plant_names = [plant.get('name', '').replace('_', ' ').title() for plant in plants]

        response = f"Perfect! For your {location}, I've found some fantastic options:\n\n"

        for i, plant in enumerate(plants, 1):
            name = plant.get('name', '').replace('_', ' ').title()
            description = plant.get('description', 'A wonderful plant choice!')
            response += f"{i}. **{name}** - {description}\n"

        response += f"\nThese are all great matches for your {location}"
        if preferences.get('experience'):
            response += f" and perfect for {preferences['experience']} plant parents"

        response += "! Would you like to know more about caring for any of these plants? 🌿"

        return response


def process_chat_message(message: str, session_id: str) -> Dict[str, Any]:
    """Main chat processing with enhanced conversational AI"""
    try:
        # Get or create conversation
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
        if any(cmd in message.lower() for cmd in ["restart", "reset", "start over", "new conversation"]):
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0
            }
            return {
                'type': 'text',
                'content': "Let's start fresh! I'm GrowVRD, and I'm absolutely passionate about helping people find their perfect plants. What kind of plant adventure are you thinking about? 🌿✨",
                'preferences': {}
            }

        # Add user message to history
        conversation['messages'].append({"role": "user", "content": message})

        # Process with AI
        try:
            new_preferences, ai_response = process_message_with_ai(
                message,
                conversation['messages'][:-1],
                conversation['preferences']
            )
        except Exception as e:
            logger.error(f"AI processing failed: {e}")
            new_preferences, ai_response = handle_message_fallback(message, conversation['preferences'])

        # Merge new preferences intelligently
        for key, value in new_preferences.items():
            if value and key not in ['ready_for_recommendations', 'conversation_tone']:
                if key == 'specific_needs' and isinstance(value, list):
                    if key not in conversation['preferences']:
                        conversation['preferences'][key] = []
                    for need in value:
                        if need not in conversation['preferences'][key]:
                            conversation['preferences'][key].append(need)
                else:
                    conversation['preferences'][key] = value

        # Update conversation state
        conversation['last_update'] = datetime.now().isoformat()

        # Determine response type
        if should_recommend_plants(conversation['preferences'], conversation['message_count']):
            # Get and present recommendations
            plants = get_smart_plant_recommendations(conversation['preferences'])

            if plants:
                response_text = create_recommendation_response(plants, conversation['preferences'], ai_response)

                conversation['messages'].append({"role": "assistant", "content": response_text})

                return {
                    'type': 'recommendation',
                    'content': response_text,
                    'data': {
                        'plants': plants,
                        'preferences': conversation['preferences']
                    },
                    'preferences': conversation['preferences']
                }
            else:
                # No plants found
                fallback_text = ai_response or "I'm having trouble finding the perfect match. Could you tell me more about your space or what specific qualities you're looking for in a plant?"

                conversation['messages'].append({"role": "assistant", "content": fallback_text})

                return {
                    'type': 'text',
                    'content': fallback_text,
                    'preferences': conversation['preferences']
                }
        else:
            # Continue conversation
            response_text = ai_response or "Tell me more! I'm here to help you find the perfect plants for your space."

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
            'content': "Oops! I had a little hiccup there. Could you try asking me again? I'm excited to help you find some amazing plants! 🌱",
            'preferences': conversations.get(session_id, {}).get('preferences', {})
        }


# Flask Routes
@app.route('/')
def home():
    return send_from_directory('static', 'chat.html')


@app.route('/chat')
def chat_interface():
    return send_from_directory('static', 'chat.html')


@app.route('/form')
def form_interface():
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)


@app.route('/api/chat', methods=['POST'])
def chat():
    """Enhanced chat API with better conversation handling"""
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))

        if not message:
            return jsonify({
                "type": "error",
                "content": "I'd love to hear from you! What can I help you with?",
                "session_id": session_id
            })

        logger.info(f"Processing: '{message}' (session: {session_id[:8]})")

        response = process_chat_message(message, session_id)
        response['session_id'] = session_id

        logger.info(f"Response type: {response.get('type')}")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Chat API error: {str(e)}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": "I'm having a moment! Could you try that again? I'm excited to help you with plants! 🌿",
            "session_id": data.get('session_id', str(uuid.uuid4()))
        })


@app.route('/api/debug', methods=['GET'])
def debug():
    """Debug endpoint"""
    return jsonify({
        "conversations_count": len(conversations),
        "openai_available": bool(openai_client),
        "perenual_enabled": PERENUAL_ENABLED,
        "environment": ENVIRONMENT,
        "recent_conversations": [
            {
                "session": sid[:8] + "...",
                "messages": len(conv.get('messages', [])),
                "preferences": conv.get('preferences', {})
            }
            for sid, conv in list(conversations.items())[-3:]
        ]
    })


@app.route('/api/health')
def health():
    return jsonify({
        "status": "healthy",
        "version": "3.0.0",
        "features": ["natural_conversation", "intelligent_context", "enhanced_ai"],
        "openai_ready": bool(openai_client),
        "timestamp": datetime.now().isoformat()
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"🌿 Starting GrowVRD v3.0 - Natural Conversational AI")
    logger.info(f"OpenAI ready: {bool(openai_client)}")
    logger.info(f"Running on: http://localhost:{port}")

    app.run(debug=ENVIRONMENT == 'development', host='0.0.0.0', port=port)