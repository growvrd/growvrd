"""
GrowVRD - Enhanced Chat-based Plant Recommendation System
Main Flask Application with Improved Conversation Flow and Follow-up Questions
"""
import os
import json
import logging
import uuid
import time
import re
from flask import Flask, request, jsonify, send_from_directory
import openai
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

# Initialize OpenAI client with API key from environment variable
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    logger.warning("OPENAI_API_KEY environment variable not set. OpenAI functionality will not work.")
else:
    openai.api_key = openai_api_key

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
    """Create a comprehensive system prompt for plant expertise with conversation flow"""
    return """You are GrowVRD, the world's most knowledgeable and friendly plant care assistant. You help people find perfect plants for their spaces through natural conversation.

CORE PERSONALITY:
- Friendly, encouraging, and genuinely excited about plants
- Ask thoughtful follow-up questions to understand their space better
- Remember everything from our conversation and build on it
- Explain plant recommendations clearly with specific reasons
- Share care tips and troubleshooting advice naturally

CONVERSATION FLOW EXPERTISE:
You should guide users through understanding:
1. WHERE they want plants (specific room/location)
2. LIGHTING conditions in that space (be specific about windows, natural light, etc.)
3. Their EXPERIENCE level and comfort with plant care
4. How much MAINTENANCE/attention they want to give
5. Any SPECIFIC preferences (plant types, functions, constraints)

ASKING FOLLOW-UP QUESTIONS:
- Always acknowledge what they've told you first
- Ask ONE specific follow-up question to get more detail
- Be conversational, not like a form ("Tell me about the lighting in your bedroom")
- Help them think about their space ("Does your kitchen get morning sun from a window?")
- Build on their answers ("Since you mentioned low maintenance, how do you feel about watering once a week?")

HANDLING FOLLOW-UPS:
- When they ask follow-up questions about recommended plants, engage enthusiastically
- Provide detailed care instructions for their specific situation
- Ask if they want to know about other plants or have other questions
- Offer to help them think through setup details (where to place it, what pot size, etc.)

RECOMMENDATION APPROACH:
- Only recommend plants when you have enough info (location + at least 2 other preferences)
- Explain WHY each plant is perfect for their specific situation
- Include care difficulty and what makes each plant succeed in their space
- Always end with "What questions do you have about these plants?" or similar

RESPONSE FORMAT:
Always respond naturally and conversationally. At the end of your response, include a JSON object with extracted preferences:

```json
{
  "location": "bedroom",
  "light": "low", 
  "experience_level": "beginner",
  "maintenance": "low",
  "plant_types": ["air purifying"],
  "conversation_stage": "recommendation_ready",
  "confidence": 0.9,
  "next_question_suggested": "What questions do you have about caring for these plants?"
}
```

CONVERSATION STAGES:
- greeting: Initial hello, asking what they're looking for
- location_discovery: Finding out where they want plants
- light_discovery: Understanding their lighting conditions
- experience_discovery: Learning about their plant experience
- maintenance_discovery: Understanding their care preferences
- preference_refinement: Getting specific preferences or constraints
- recommendation_ready: Have enough info to recommend plants
- follow_up: User asking about recommended plants
- care_discussion: Discussing specific plant care

Remember: Keep the conversation flowing naturally. Users should feel like they're talking to a knowledgeable friend who's genuinely interested in helping them succeed with plants!"""


def analyze_conversation_stage(conversation_history: List[Dict], current_preferences: Dict) -> str:
    """Analyze what stage the conversation is in"""

    # Check what preferences we have
    has_location = 'location' in current_preferences and current_preferences['location']
    has_light = 'light' in current_preferences and current_preferences['light']
    has_experience = 'experience_level' in current_preferences and current_preferences['experience_level']
    has_maintenance = 'maintenance' in current_preferences and current_preferences['maintenance']

    # Check recent messages for context
    recent_messages = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
    recent_text = ' '.join([msg['content'].lower() for msg in recent_messages if msg['role'] == 'user'])

    # Check if user is asking follow-up questions about plants
    follow_up_indicators = [
        'care for', 'how do i', 'water', 'fertilize', 'light', 'soil', 'repot', 'problems',
        'dying', 'yellow', 'brown', 'drooping', 'what if', 'tell me more', 'how often'
    ]

    care_discussion_indicators = [
        'watering', 'fertilizing', 'pruning', 'repotting', 'troubleshoot', 'problem',
        'sick', 'healthy', 'growing', 'placement'
    ]

    if any(indicator in recent_text for indicator in follow_up_indicators):
        if any(indicator in recent_text for indicator in care_discussion_indicators):
            return ConversationStage.CARE_DISCUSSION
        return ConversationStage.FOLLOW_UP

    # Determine stage based on what we know
    if not has_location:
        return ConversationStage.LOCATION_DISCOVERY
    elif not has_light:
        return ConversationStage.LIGHT_DISCOVERY
    elif not has_experience:
        return ConversationStage.EXPERIENCE_DISCOVERY
    elif not has_maintenance:
        return ConversationStage.MAINTENANCE_DISCOVERY
    elif has_location and has_light and (has_experience or has_maintenance):
        # Check if user seems to want more specific preferences
        if len(conversation_history) < 6:  # Early in conversation
            return ConversationStage.PREFERENCE_REFINEMENT
        return ConversationStage.RECOMMENDATION_READY
    else:
        return ConversationStage.GREETING


def extract_preferences_with_openai(message: str, conversation_history: List[Dict], current_preferences: Dict) -> Tuple[
    Dict[str, Any], str]:
    """Enhanced preference extraction using OpenAI with conversation flow awareness"""
    try:
        # Analyze conversation stage
        conversation_stage = analyze_conversation_stage(conversation_history, current_preferences)

        # Build complete conversation context
        context_messages = [
            {"role": "system", "content": create_plant_expert_system_prompt()}
        ]

        # Add conversation history with stage context
        if conversation_history:
            context_messages.extend(conversation_history[-8:])  # Last 8 messages for context

        # Add current message with stage information
        stage_context = f"""
        Current conversation stage: {conversation_stage}
        Current known preferences: {json.dumps(current_preferences)}

        User message: {message}

        Based on the conversation stage and what we already know, respond appropriately:
        - If we need more info, ask ONE specific follow-up question
        - If user is asking about plants, provide detailed care information
        - If ready for recommendations, provide 2-3 great plant suggestions
        - Always acknowledge what they've shared and build on it naturally
        """

        context_messages.append({"role": "user", "content": stage_context})

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=context_messages,
            max_tokens=600,
            temperature=0.4  # Slightly more creative for natural conversation
        )

        response_content = response.choices[0].message.content

        # Extract JSON preferences from response
        preferences = {}
        natural_response = response_content

        try:
            # Look for JSON in the response
            json_start = response_content.find('```json')
            if json_start != -1:
                json_start = response_content.find('{', json_start)
                json_end = response_content.find('```', json_start)
                if json_end == -1:
                    json_end = len(response_content)
                json_str = response_content[json_start:json_end]
            else:
                # Look for JSON without markdown
                json_start = response_content.find('{')
                json_end = response_content.rfind('}') + 1
                json_str = response_content[json_start:json_end]

            if json_start != -1 and json_end > json_start:
                preferences = json.loads(json_str)
                # Remove JSON from natural response
                natural_response = response_content[:json_start].strip()
                if not natural_response:
                    natural_response = response_content[json_end:].strip()

        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"No valid JSON found in OpenAI response: {e}")

        return preferences, natural_response

    except Exception as e:
        logger.error(f"OpenAI preference extraction failed: {str(e)}")
        return {}, f"I'm here to help you find great plants! Could you tell me more about what you're looking for?"


def should_provide_recommendations(preferences: Dict, conversation_stage: str, message_count: int) -> bool:
    """Determine if we should provide plant recommendations"""

    # Always provide recommendations if explicitly requested
    if conversation_stage == ConversationStage.RECOMMENDATION_READY:
        return True

    # Minimum requirements: location + one other preference
    has_location = 'location' in preferences and preferences['location']
    has_other_prefs = any(key in preferences and preferences[key] for key in
                          ['light', 'experience_level', 'maintenance', 'plant_types'])

    # Provide recommendations if we have minimum info
    if has_location and has_other_prefs:
        return True

    # If conversation is getting long, provide recommendations with caveats
    if message_count > 8 and has_location:
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


def generate_follow_up_response_with_openai(message: str, conversation_history: List[Dict], preferences: Dict) -> str:
    """Generate follow-up responses using OpenAI for plant care questions"""
    if not openai_api_key:
        return "I'd love to help you with that! Could you tell me more specifically what you'd like to know?"

    try:
        # Create context for follow-up questions
        context = f"""
        User preferences so far: {json.dumps(preferences, indent=2)}

        The user is asking a follow-up question about plants or plant care: "{message}"

        Recent conversation context:
        {json.dumps(conversation_history[-4:], indent=2)}

        Provide a helpful, detailed response that:
        1. Directly answers their question
        2. Gives specific care instructions if they're asking about care
        3. Relates back to their preferences and situation
        4. Asks a natural follow-up question to keep the conversation going
        5. Shows enthusiasm about helping them succeed with plants

        Be conversational and encouraging!
        """

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": create_plant_expert_system_prompt()},
                {"role": "user", "content": context}
            ],
            max_tokens=400,
            temperature=0.6
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"OpenAI follow-up generation failed: {str(e)}")
        return "That's a great question! I'd love to help you with more specific plant care advice. What exactly would you like to know more about?"


def process_chat_message(message: str, session_id: str) -> Dict[str, Any]:
    """Process chat message with enhanced conversation flow and follow-up handling"""
    try:
        # Get or initialize conversation
        if session_id not in conversations:
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0,
                'conversation_stage': ConversationStage.GREETING
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
                'message_count': 0,
                'conversation_stage': ConversationStage.GREETING
            }
            return {
                'type': 'text',
                'content': "Let's start fresh! I'm here to help you find the perfect plants for your space. What kind of plants are you looking for? 🌿",
                'preferences': {}
            }

        # Add user message to history
        conversation['messages'].append({"role": "user", "content": message})

        # Analyze conversation stage
        conversation_stage = analyze_conversation_stage(
            conversation['messages'],
            conversation['preferences']
        )
        conversation['conversation_stage'] = conversation_stage

        # Extract preferences using OpenAI with full conversation context
        new_preferences, natural_response = extract_preferences_with_openai(
            message,
            conversation['messages'][:-1],  # Don't include the current message we just added
            conversation['preferences']
        )

        # Update stored preferences
        for key, value in new_preferences.items():
            if value and key not in ['confidence', 'conversation_stage', 'next_question_suggested']:
                if key in ['plant_types'] and isinstance(value, list):
                    # Merge arrays
                    if key not in conversation['preferences']:
                        conversation['preferences'][key] = []
                    for item in value:
                        if item and item not in conversation['preferences'][key]:
                            conversation['preferences'][key].append(item)
                else:
                    conversation['preferences'][key] = value

        logger.info(f"Session {session_id}: Stage={conversation_stage}, Preferences={conversation['preferences']}")

        # Handle different conversation stages
        if conversation_stage in [ConversationStage.FOLLOW_UP, ConversationStage.CARE_DISCUSSION]:
            # User is asking follow-up questions about plants or care
            follow_up_response = generate_follow_up_response_with_openai(
                message,
                conversation['messages'],
                conversation['preferences']
            )

            conversation['messages'].append({"role": "assistant", "content": follow_up_response})

            return {
                'type': 'follow_up',
                'content': follow_up_response,
                'preferences': conversation['preferences'],
                'conversation_stage': conversation_stage
            }

        # Check if we should provide recommendations
        should_recommend = should_provide_recommendations(
            conversation['preferences'],
            conversation_stage,
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

                # Use natural response from OpenAI or generate one
                if not natural_response or len(natural_response) < 50:
                    location_display = conversation['preferences'].get('location', 'space').replace('_', ' ')
                    plant_names = [plant.get('name', '').replace('_', ' ').title() for plant in top_plants]
                    natural_response = f"Perfect! For your {location_display}, I'd recommend: {', '.join(plant_names)}. These plants are great matches for your preferences!"

                # Always add a follow-up question to keep conversation going
                if not any(q in natural_response.lower() for q in ['?', 'question', 'tell me', 'what do you']):
                    natural_response += " What questions do you have about caring for these plants?"

                conversation['messages'].append({"role": "assistant", "content": natural_response})

                return {
                    'type': 'recommendation',
                    'content': natural_response,
                    'data': {
                        'plants': top_plants,
                        'preferences': conversation['preferences']
                    },
                    'preferences': conversation['preferences'],
                    'conversation_stage': ConversationStage.RECOMMENDATION_READY
                }
            else:
                # No plants found - ask for more info
                fallback_response = natural_response or "I'd love to help you find the perfect plants! To give you the best recommendations, could you tell me a bit more about your space? For example, which room are you thinking about, and how much light does it get?"

                conversation['messages'].append({"role": "assistant", "content": fallback_response})

                return {
                    'type': 'text',
                    'content': fallback_response,
                    'preferences': conversation['preferences'],
                    'conversation_stage': conversation_stage
                }
        else:
            # Need more information - use OpenAI's natural response with follow-up
            response_text = natural_response or "Tell me more about what you're looking for in a plant! I'm here to help you find something perfect for your space."

            # Make sure we're asking a follow-up question
            if not any(q in response_text.lower() for q in ['?', 'tell me', 'what', 'how', 'where']):
                if not conversation['preferences'].get('location'):
                    response_text += " What room are you thinking about?"
                elif not conversation['preferences'].get('light'):
                    response_text += " How much light does that space get?"
                else:
                    response_text += " What else would you like me to know about your preferences?"

            conversation['messages'].append({"role": "assistant", "content": response_text})

            return {
                'type': 'text',
                'content': response_text,
                'preferences': conversation['preferences'],
                'conversation_stage': conversation_stage
            }

    except Exception as e:
        logger.error(f"Error in process_chat_message: {str(e)}", exc_info=True)
        return {
            'type': 'error',
            'content': "I'm sorry, I encountered an error. Could you try rephrasing your message?",
            'preferences': conversations.get(session_id, {}).get('preferences', {}),
            'conversation_stage': ConversationStage.GREETING
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
    """API endpoint for chat interactions with enhanced conversation flow"""
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

        # Process the message
        response = process_chat_message(message, session_id)
        response['session_id'] = session_id

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
        "openai_enabled": bool(openai_api_key),
        "perenual_enabled": PERENUAL_ENABLED,
        "environment": ENVIRONMENT,
        "cache_size": len(perenual_cache),
        "sample_conversations": [
            {
                "session_id": sid[:8] + "...",
                "message_count": conv.get('message_count', 0),
                "stage": conv.get('conversation_stage', 'unknown'),
                "preferences": conv.get('preferences', {})
            }
            for sid, conv in list(conversations.items())[:3]
        ]
    }

    return jsonify(debug_info)


@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.1.0",
        "openai_ready": bool(openai_api_key),
        "perenual_ready": PERENUAL_ENABLED,
        "features": ["conversation_flow", "follow_up_questions", "stage_tracking"]
    })


# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    host = '0.0.0.0'
    debug = ENVIRONMENT == 'development'

    logger.info(f"Starting Enhanced GrowVRD v2.1 on {host}:{port}")
    logger.info(f"OpenAI enabled: {bool(openai_api_key)}")
    logger.info(f"Perenual enabled: {PERENUAL_ENABLED}")
    logger.info("Features: Conversation flow, follow-up questions, stage tracking")

    app.run(debug=debug, host=host, port=port)