"""
GrowVRD - Chat-based Plant Recommendation System with Perenual API Integration
Main Flask Application
"""
import os
import json
import logging
import uuid
import time
import re
from flask import Flask, request, jsonify, send_from_directory, redirect
import openai
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

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
try:
    from api.perenual_api import search_species, get_species_details, PerenualAPIError
    from api.perenual_integration import (
        search_and_import_plants,
        find_and_import_plants_for_environment,
        map_perenual_to_growvrd,
        enrich_plant_with_care_guide,
        create_test_plant
    )

    logger.info("Successfully imported Perenual API integration")
    PERENUAL_ENABLED = True
except ImportError as e:
    logger.error(f"Failed to import Perenual API integration: {str(e)}")
    PERENUAL_ENABLED = False

# Create Flask app
app = Flask(__name__, static_folder='static')

# In-memory conversation storage
conversations = {}

# In-memory cache for Perenual data to avoid repeated API calls
perenual_cache = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds


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


def extract_plant_preferences(message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract plant preferences from user message with improved reliability for basic information.

    Args:
        message: User's message
        session_id: Optional session ID to provide conversation context

    Returns:
        Dictionary with extracted preferences
    """
    # First try to identify location through simple pattern matching
    message_lower = message.lower()
    preferences = {
        "location": None,
        "light": None,
        "experience_level": None,
        "maintenance": None,
        "plant_types": [],
        "additional_preferences": []
    }

    # Direct pattern matching for location
    location_patterns = {
        r"\b(kitchen|cooking|cook|food)\b": "kitchen",
        r"\b(living room|livingroom|lounge|family room)\b": "living_room",
        r"\b(bedroom|bed room|sleeping|sleep)\b": "bedroom",
        r"\b(bathroom|bath|shower|toilet)\b": "bathroom",
        r"\b(office|study|desk|workspace|work space)\b": "office",
        r"\b(balcony|patio|terrace|outdoor|outside)\b": "balcony"
    }

    for pattern, location in location_patterns.items():
        if re.search(pattern, message_lower):
            preferences["location"] = location
            logger.info(f"Pattern matching found location: {location}")
            break

    # Direct pattern matching for light conditions
    light_patterns = {
        r"\b(low light|dark|dim|shadowy|shady|shade|no sun|hardly any sun|little sun|not much sun)\b": "low",
        r"\b(medium light|moderate light|some light|partial light|indirect light)\b": "medium",
        r"\b(bright indirect|filtered light|bright shade|plenty of light)\b": "bright_indirect",
        r"\b(direct light|full sun|sunny|sunshine|direct sun|lots of sun)\b": "direct"
    }

    for pattern, light in light_patterns.items():
        if re.search(pattern, message_lower):
            preferences["light"] = light
            logger.info(f"Pattern matching found light condition: {light}")
            break

    # Pattern matching for experience level
    experience_patterns = {
        r"\b(beginner|new|novice|start|starting|never|inexperienced|first time|new to)\b": "beginner",
        r"\b(intermediate|some experience|familiar|have grown|not new)\b": "intermediate",
        r"\b(advanced|expert|experienced|master|very familiar|many years|green thumb)\b": "advanced"
    }

    for pattern, level in experience_patterns.items():
        if re.search(pattern, message_lower):
            preferences["experience_level"] = level
            logger.info(f"Pattern matching found experience level: {level}")
            break

    # Pattern matching for maintenance
    maintenance_patterns = {
        r"\b(low maintenance|easy|minimal|neglect|busy|no time|forgetful|lazy|simple|hardy|resilient|survive)\b": "low",
        r"\b(medium maintenance|moderate|some care|weekly|regular|normal)\b": "medium",
        r"\b(high maintenance|demanding|attention|careful|frequent|daily|lots of care|high care)\b": "high"
    }

    for pattern, level in maintenance_patterns.items():
        if re.search(pattern, message_lower):
            preferences["maintenance"] = level
            logger.info(f"Pattern matching found maintenance level: {level}")
            break

    # Pattern matching for common plant types
    plant_type_patterns = {
        r"\b(succulents|succulent|cactus|cacti|aloe|jade)\b": "succulent",
        r"\b(herb|herbs|basil|mint|rosemary|thyme|oregano|sage|edible)\b": "herb",
        r"\b(fern|ferns|boston fern|maidenhair)\b": "fern",
        r"\b(air plant|air plants|tillandsia)\b": "air plant",
        r"\b(trailing|hanging|vine|vining|pothos|ivy|philodendron)\b": "trailing",
        r"\b(flowering|flowers|orchid|peace lily|blooms|blooming)\b": "flowering",
        r"\b(large|big|tall|statement|monstera|fiddle|fig)\b": "large",
        r"\b(palm|palms|tree|trees)\b": "palm",
        r"\b(air purifying|air purification|clean air|purify)\b": "air purifying",
        r"\b(snake plant|pothos|zz plant|spider plant|peace lily)\b": "popular houseplant"
    }

    for pattern, plant_type in plant_type_patterns.items():
        if re.search(pattern, message_lower):
            if plant_type not in preferences["plant_types"]:
                preferences["plant_types"].append(plant_type)
                logger.info(f"Pattern matching found plant type: {plant_type}")

    # Additional preferences
    additional_patterns = {
        r"\b(pet friendly|pet safe|non toxic|nontoxic|cats|dogs|children|kids|baby)\b": "pet friendly",
        r"\b(colorful|colourful|colors|colours|bright)\b": "colorful",
        r"\b(unique|unusual|rare|exotic|special)\b": "unique",
        r"\b(small|tiny|mini|compact|desktop|tabletop)\b": "small",
        r"\b(tropical|tropicals|jungle|rainforest)\b": "tropical",
        r"\b(modern|contemporary|sleek|minimalist)\b": "modern style",
        r"\b(traditional|classic|timeless)\b": "traditional style"
    }

    for pattern, pref in additional_patterns.items():
        if re.search(pattern, message_lower):
            if pref not in preferences["additional_preferences"]:
                preferences["additional_preferences"].append(pref)
                logger.info(f"Pattern matching found additional preference: {pref}")

    # Then try OpenAI to get more nuanced preferences
    if openai_api_key:
        try:
            # Context from conversation history if available
            context = ""
            if session_id and session_id in conversations:
                prev_messages = conversations[session_id].get('messages', [])
                if prev_messages:
                    # Get last few message exchanges for context
                    recent_messages = prev_messages[-6:] if len(prev_messages) > 6 else prev_messages
                    context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
                    context = f"Previous conversation:\n{context}\n\n"

            # ENHANCED: Improved prompt with more gardening expertise
            prompt = f"""
            {context}
            You are a professional botanist and plant specialist. Analyze this message about plants and extract ANY preferences mentioned, both explicit and implicit.

            User message: "{message}"

            Look for nuanced preferences about these aspects, considering synonyms and gardening terminology:

            - Location: specific rooms or locations (living room, bedroom, bathroom, kitchen, office, balcony, etc.)
            - Light conditions: light levels (low/dark/dim/north-facing, medium/east or west-facing, bright indirect/south-facing but filtered, direct/full sun)
            - Experience level: gardening skill or knowledge (beginner/newbie/first-time plant parent, intermediate/some experience, advanced/expert/master gardener)
            - Maintenance: care needs and time investment (low/easy/neglect-resistant/set-and-forget, medium/weekly care needed, high/daily attention required)
            - Size: plant dimensions (small/compact/tabletop/desktop, medium/shelf-sized, large/floor/statement)
            - Growth habits: trailing/climbing/upright/bushy/spreading
            - Special features: air purifying, flowering, scented/aromatic, edible, medicinal, variegated foliage
            - Pet/child safety: non-toxic, safe for pets, child-friendly
            - Aesthetics: color preferences, leaf patterns, architectural interest
            - Specific plant types or botanical families mentioned
            - Environmental factors: humidity, temperature, drafts, air conditioning

            Return a JSON object with these fields:
            {
            "location": "",
            "light": "",
            "experience_level": "",
            "maintenance": "",
            "plant_types": [],
            "additional_preferences": []
            }

            If something isn't mentioned, leave the field empty.
            Use your botanical expertise to read between the lines and identify implicit preferences.
            Format arrays as strings of comma-separated values.
            Add specific plant names, botanical families, or types to "plant_types" array.
            """

            # Call the OpenAI API with a more sophisticated system message
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system",
                     "content": "You are a professional botanist and horticultural expert with 30 years of experience in plant identification, care, and matching plants to specific growing environments. You specialize in extracting detailed plant preferences from casual conversations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.2
            )

            # Get the response text and parse as JSON
            json_str = response.choices[0].message.content.strip()

            # Remove any markdown formatting if present
            if "```json" in json_str:
                # Extract just the JSON part from markdown code block
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].strip()

            ai_preferences = json.loads(json_str)
            logger.info(f"OpenAI extracted preferences: {ai_preferences}")

            # Merge OpenAI results with pattern matching, giving priority to OpenAI for completeness
            for key in ["location", "light", "experience_level", "maintenance"]:
                if ai_preferences.get(key) and not preferences.get(key):
                    preferences[key] = ai_preferences.get(key)

            # Merge arrays
            for key in ["plant_types", "additional_preferences"]:
                if key in ai_preferences and ai_preferences[key]:
                    # Handle both string and array format
                    ai_values = ai_preferences[key]
                    if isinstance(ai_values, str):
                        ai_values = [item.strip() for item in ai_values.split(',')]

                    for item in ai_values:
                        if item and item not in preferences[key]:
                            preferences[key].append(item)

        except Exception as e:
            logger.error(f"Error extracting preferences with OpenAI: {str(e)}")
            logger.error(f"Will continue with pattern matching results only: {preferences}")

    # Fill in defaults if we have nothing detected
    if not any([preferences["location"], preferences["light"], preferences["experience_level"],
                preferences["maintenance"], preferences["plant_types"], preferences["additional_preferences"]]):
        # Try looking for any basic room name in the text as last resort
        basic_rooms = ["kitchen", "living room", "bedroom", "bathroom", "office"]
        for room in basic_rooms:
            if room in message_lower:
                preferences["location"] = room.replace(" ", "_")
                break

    # Log the final results of preference extraction
    logger.info(f"Final extracted preferences: {preferences}")
    return preferences


def get_plants_from_perenual(preferences: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get plants from Perenual API based on user preferences.

    Args:
        preferences: User preferences dictionary
        limit: Maximum number of plants to return

    Returns:
        List of plants in GrowVRD format
    """
    if not PERENUAL_ENABLED:
        logger.warning("Perenual API integration not enabled")
        return []

    try:
        # Check if we have specific location and light preferences
        location = preferences.get('location')
        light = preferences.get('light')
        maintenance = preferences.get('maintenance')
        plant_types = preferences.get('plant_types', [])

        # Create a cache key based on preferences
        cache_key = f"l:{location or 'any'}_lt:{light or 'any'}_m:{maintenance or 'any'}_pt:{','.join(plant_types)}"

        # Check if we have cached results
        cached_plants = get_cached_perenual_plants(cache_key)
        if cached_plants:
            logger.info(f"Using cached Perenual plants for {cache_key}")
            return cached_plants

        # Strategy 1: If we have location and light, find plants for that environment
        if location and light:
            logger.info(
                f"Searching Perenual for plants matching: location={location}, light={light}, maintenance={maintenance}")
            plants = find_and_import_plants_for_environment(
                location=location,
                light_level=light,
                maintenance_level=maintenance,
                limit=limit
            )

            if plants:
                logger.info(f"Found {len(plants)} plants from Perenual for environment")
                cache_perenual_plants(cache_key, plants)
                return plants

        # Strategy 2: If we have specific plant types, search for those
        if plant_types:
            all_plants = []
            for plant_type in plant_types[:2]:  # Limit to first 2 types to avoid too many API calls
                logger.info(f"Searching Perenual for plant type: {plant_type}")
                plants = search_and_import_plants(
                    query=plant_type,
                    limit=limit // len(plant_types[:2]),  # Divide limit among search terms
                    save_to_database=False
                )
                all_plants.extend(plants)

            if all_plants:
                logger.info(f"Found {len(all_plants)} plants from Perenual for plant types")
                cache_perenual_plants(cache_key, all_plants)
                return all_plants

        # Strategy 3: If we have additional preferences, try searching with those
        additional_prefs = preferences.get('additional_preferences', [])
        if additional_prefs:
            search_term = additional_prefs[0]  # Use the first preference as search term
            logger.info(f"Searching Perenual for term: {search_term}")
            plants = search_and_import_plants(
                query=search_term,
                limit=limit,
                save_to_database=False
            )

            if plants:
                logger.info(f"Found {len(plants)} plants from Perenual for search term")
                cache_perenual_plants(cache_key, plants)
                return plants

        # Strategy 4: If just location is specified, try a generic search based on location
        if location and not light and not plant_types:
            logger.info(f"Searching Perenual for location-based plants: {location}")
            location_search_terms = {
                "kitchen": "herb culinary",
                "living_room": "houseplant decorative",
                "bedroom": "air purifying calming",
                "bathroom": "humidity tolerant",
                "office": "low light desk plant",
                "balcony": "outdoor container"
            }
            search_term = location_search_terms.get(location, "indoor plant")
            plants = search_and_import_plants(
                query=search_term,
                limit=limit,
                save_to_database=False
            )

            if plants:
                logger.info(f"Found {len(plants)} plants from Perenual for location-based search")
                cache_perenual_plants(cache_key, plants)
                return plants

        # If all strategies fail, return empty list
        logger.warning("No plants found from Perenual API")
        return []

    except Exception as e:
        logger.error(f"Error getting plants from Perenual: {str(e)}")
        return []


def generate_simple_response(preferences: Dict[str, Any], plants: List[Dict[str, Any]]) -> str:
    """
    Generate a simple response without using OpenAI when plants are found.

    Args:
        preferences: User preferences dictionary
        plants: List of plant dictionaries

    Returns:
        A natural language response about the plants
    """
    # Format location for display
    location_display = preferences.get('location', '').replace('_', ' ')

    # If we don't have any plants, return a simple message
    if not plants:
        return f"I'm having trouble finding plants that match your specific requirements. Could you tell me more about your space or consider adjusting some preferences like light conditions or maintenance level?"

    # Get the names of the found plants
    plant_names = []
    for plant in plants:
        name = plant.get('name', '').replace('_', ' ').title()
        if name:
            plant_names.append(name)

    # Generate a more detailed response based on the preferences and plants
    if location_display:
        response = f"Based on your preferences, here are some excellent plants for your {location_display}: "
    else:
        response = f"Based on your preferences, here are some plants I'd recommend: "

    response += ", ".join(plant_names[:-1]) + (
        f" and {plant_names[-1]}" if len(plant_names) > 1 else plant_names[0]) + "."

    # Add some details about the first plant with more specific care info
    if plants:
        plant = plants[0]
        name = plant.get('name', '').replace('_', ' ').title()
        scientific_name = plant.get('scientific_name', '').replace('_', ' ')
        light_needs = plant.get('natural_sunlight_needs', '').replace('_', ' ')
        water_freq = plant.get('water_frequency_days', 7)
        description = plant.get('description', '')
        humidity = plant.get('humidity_preference', 'medium')

        response += f"\n\nThe {name} ({scientific_name}) is an excellent choice. {description[:100]}... "

        # Add more specific care tips
        response += f"It thrives in {light_needs} light and prefers {humidity} humidity. Water it every {water_freq} days, "

        # Add a more specific watering tip
        if water_freq <= 3:
            response += "keeping the soil consistently moist but not soggy. "
        elif water_freq <= 7:
            response += "allowing the top inch of soil to dry out between waterings. "
        else:
            response += "letting the soil dry out completely between waterings. "

        # Add a maintenance tip
        maintenance = plant.get('maintenance', '').lower()
        if 'low' in maintenance:
            response += f"The {name} is very forgiving and can bounce back even if you forget to water it occasionally. "
        elif 'high' in maintenance:
            response += f"The {name} appreciates regular attention, including occasional misting and rotation for even growth. "

    # Add a tailored tip based on preferences
    light = preferences.get('light', '')
    if light == 'low':
        response += "\n\nWith your low light conditions, make sure to dust the leaves occasionally to maximize light absorption. Even low-light plants need to make the most of the light they receive."
    elif light == 'direct':
        response += "\n\nWith your direct light conditions, monitor your plants for signs of leaf burn, especially in summer months. Rotating your plants weekly promotes even growth and prevents leaning."

    # Add a question to continue the conversation
    additional_prefs = preferences.get('additional_preferences', [])
    if 'pet friendly' in additional_prefs:
        response += "\n\nWould you like more specific information about keeping these plants safe around your pets?"
    else:
        response += "\n\nWould you like more specific care tips for any of these plants?"

    return response


def process_chat_with_ai(message: str, session_id: str) -> Dict[str, Any]:
    """
    Process a chat message using a combination of OpenAI and Perenual API with improved flexibility.

    Args:
        message: User's message
        session_id: Unique session identifier

    Returns:
        Response dictionary with content and data
    """
    try:
        # Get or initialize conversation state
        if session_id not in conversations:
            conversations[session_id] = {
                'messages': [{"role": "assistant",
                              "content": "Hi! I'm your GrowVRD plant assistant with expertise in indoor and outdoor gardening. I can help you find the perfect plants for your space and provide detailed care advice. What kind of plants are you looking for today?"}],
                'preferences': {},
                'last_update': datetime.now().isoformat()
            }

        conversation = conversations[session_id]

        # Add user message to conversation history
        conversation['messages'].append({"role": "user", "content": message})

        # Check for simple commands
        message_lower = message.lower()
        if "restart" in message_lower or "reset" in message_lower or "start over" in message_lower:
            conversations[session_id] = {
                'messages': [
                    {"role": "assistant",
                     "content": "Let's start over! I'm here to help you find the perfect plants for your space. What kind of plants are you interested in, or which room are you looking to add some greenery to?"}],
                'preferences': {},
                'last_update': datetime.now().isoformat()
            }
            return {
                'type': 'text',
                'content': "Let's start over! I'm here to help you find the perfect plants for your space. What kind of plants are you interested in, or which room are you looking to add some greenery to?"
            }

        # Extract preferences from message
        new_preferences = extract_plant_preferences(message, session_id)

        # Debug log for troubleshooting
        logger.info(f"New extracted preferences: {new_preferences}")
        logger.info(f"Current stored preferences: {conversation['preferences']}")

        # Update stored preferences with new ones
        for key, value in new_preferences.items():
            if value and key not in ["additional_preferences", "plant_types"]:  # Skip empty values and special arrays
                conversation['preferences'][key] = value

        # Merge array preferences
        for key in ["additional_preferences", "plant_types"]:
            if key in new_preferences and new_preferences[key]:
                if key not in conversation['preferences']:
                    conversation['preferences'][key] = []
                for pref in new_preferences[key]:
                    if pref and pref not in conversation['preferences'][key]:
                        conversation['preferences'][key].append(pref)

        # Log current conversation state
        logger.info(f"Updated preferences: {conversation['preferences']}")

        # Check if we have enough preferences to get plant recommendations
        has_location = 'location' in conversation['preferences'] and conversation['preferences']['location']
        has_plant_types = 'plant_types' in conversation['preferences'] and conversation['preferences']['plant_types']
        has_search_terms = 'additional_preferences' in conversation['preferences'] and conversation['preferences'][
            'additional_preferences']

        logger.info(
            f"Recommendation check - has_location: {has_location}, has_plant_types: {has_plant_types}, has_search_terms: {has_search_terms}")

        # Second level fallback - extract location from direct message parsing if AI extraction failed
        if not has_location and any(room in message_lower for room in
                                    ["kitchen", "living room", "bedroom", "bathroom", "office", "balcony"]):
            for room, code in {
                "kitchen": "kitchen",
                "living room": "living_room",
                "bedroom": "bedroom",
                "bathroom": "bathroom",
                "office": "office",
                "balcony": "balcony"
            }.items():
                if room in message_lower:
                    logger.info(f"Fallback location detection found: {room}")
                    conversation['preferences']["location"] = code
                    has_location = True
                    break

        # Add convenience/low maintenance as a default preference if mentioned
        if "convenient" in message_lower or "easy" in message_lower or "low maintenance" in message_lower:
            conversation['preferences']["maintenance"] = "low"

        # If user is looking for kitchen plants, default to herbs if no specific type mentioned
        if has_location and conversation['preferences']["location"] == "kitchen" and not has_plant_types:
            if not "herb" in conversation['preferences'].get("plant_types", []):
                if "plant_types" not in conversation['preferences']:
                    conversation['preferences']["plant_types"] = []
                conversation['preferences']["plant_types"].append("herb")
                has_plant_types = True

        if has_location or has_plant_types or has_search_terms:
            # We have enough preferences to attempt plant recommendations

            # First try to get plants from Perenual API if enabled
            plants_data = []
            if PERENUAL_ENABLED:
                plants_data = get_plants_from_perenual(conversation['preferences'])

            # Fall back to filtered mock data if Perenual fails or is disabled
            if not plants_data:
                logger.info("Using mock plant data with filters")
                mock_plants = get_mock_plants()

                # Only filter on available preferences to avoid over-filtering
                filter_criteria = {}
                for key in ['location']:
                    if key in conversation['preferences'] and conversation['preferences'][key]:
                        filter_criteria[key] = conversation['preferences'][key]

                # Apply minimal filtering first - just location
                plants_data = filter_plants(mock_plants, filter_criteria)

                # If we got plants with minimal filtering, then apply more filters
                if plants_data:
                    # Now try more filters if we have them
                    more_filter_criteria = filter_criteria.copy()
                    for key in ['light', 'experience_level', 'maintenance']:
                        if key in conversation['preferences'] and conversation['preferences'][key]:
                            more_filter_criteria[key] = conversation['preferences'][key]

                    # Only apply additional filters if they exist
                    if len(more_filter_criteria) > len(filter_criteria):
                        more_filtered = filter_plants(mock_plants, more_filter_criteria)
                        # Only use the more filtered results if we got something
                        if more_filtered:
                            plants_data = more_filtered

            # Fallback - if we have a location but no plants were found, give some default plants for that location
            if not plants_data and has_location:
                mock_plants = get_mock_plants()
                location = conversation['preferences']['location']

                # Manually find some plants for common locations
                default_plants = []
                for plant in mock_plants:
                    comp_locs = plant.get('compatible_locations', '')
                    if isinstance(comp_locs, str):
                        comp_locs = comp_locs.split(',')

                    # If this plant works in the requested location, add it
                    if location in comp_locs:
                        default_plants.append(plant)

                # Use up to 3 default plants if found
                if default_plants:
                    logger.info(f"Using {len(default_plants)} default plants for {location}")
                    plants_data = default_plants[:3]

            # Log filtering results
            logger.info(f"Found {len(plants_data)} matching plants")

            if plants_data:
                # Limit to top 3 plants
                top_plants = plants_data[:3]

                # Try to use OpenAI for a natural response, fall back to template if unavailable
                response_text = ""
                if openai_api_key:
                    try:
                        # Generate a complete response with OpenAI
                        plant_info = []
                        for plant in top_plants:
                            plant_name = plant.get('name', '').replace('_', ' ').title()
                            scientific_name = plant.get('scientific_name', '').replace('_', ' ')
                            light_needs = plant.get('natural_sunlight_needs', '').replace('_', ' ')
                            maintenance = plant.get('maintenance', '').replace('_', ' ')
                            water_frequency = plant.get('water_frequency_days', 7)
                            difficulty = plant.get('difficulty', 5)
                            humidity = plant.get('humidity_preference', 'medium')

                            plant_info.append(
                                f"{plant_name} ({scientific_name}): Light needs: {light_needs}, Maintenance: {maintenance}, " +
                                f"Water frequency: every {water_frequency} days, Difficulty: {difficulty}/10, " +
                                f"Humidity preference: {humidity}"
                            )

                        plants_summary = "\n".join(plant_info)

                        # ENHANCED: More detailed system message and response prompt
                        system_message = """You are a master horticulturist and plant expert with 30+ years of experience growing indoor and outdoor plants.
                        You deeply understand plant biology, care requirements, and environmental adaptations.
                        You communicate like a knowledgeable friend who's passionate about helping others succeed with plants.
                        Share specific, actionable advice based on botanical science, not generic tips.
                        Include interesting facts about plants when relevant and explain the "why" behind your recommendations.
                        Your tone is warm, encouraging, and conversational while demonstrating deep expertise.
                        """

                        response_prompt = f"""
                        The user has these preferences for plants:
                        {json.dumps(conversation['preferences'], indent=2)}

                        I've found {len(top_plants)} plants that match their criteria:
                        {plants_summary}

                        Generate a friendly, helpful response that:
                        1. Acknowledges their specific preferences (location, light, etc.) in a personalized way
                        2. Explains why each plant is an excellent match for their specific environment, using botanical reasoning
                        3. For the best-matching plant, provide 2-3 specific care tips that are NOT obvious (beyond basic watering)
                        4. Share one interesting fact about one of the plants (origin, history, unique properties)
                        5. Suggest a companion plant that would work well with these recommendations
                        6. Briefly mention a potential challenge they might face and a simple solution
                        7. End with a natural follow-up question about their plant preferences or environment

                        Make your response conversational and engaging while demonstrating genuine plant expertise.
                        Include specific details that show your deep botanical knowledge.
                        Avoid generic advice like "water when soil is dry" - provide more specific actionable guidance.
                        Keep your total response under 250 words for readability.
                        """

                        openai_response = openai.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": response_prompt}
                            ],
                            max_tokens=500,
                            temperature=0.7
                        )

                        response_text = openai_response.choices[0].message.content.strip()
                    except Exception as e:
                        logger.error(f"Error generating OpenAI response: {str(e)}")
                        # Fall back to template response
                        response_text = generate_simple_response(conversation['preferences'], top_plants)
                else:
                    # No OpenAI key, use template response
                    response_text = generate_simple_response(conversation['preferences'], top_plants)

                conversation['messages'].append({"role": "assistant", "content": response_text})

                return {
                    'type': 'recommendation',
                    'content': response_text,
                    'data': {
                        'plants': top_plants,
                        'preferences': conversation['preferences']
                    }
                }
            else:
                # No plants match the criteria, but we should still try to be helpful
                # ENHANCED: Use OpenAI for more nuanced "no results" responses
                if openai_api_key:
                    try:
                        system_message = """You are a helpful plant expert. When no perfect plants match a user's criteria,
                        you can suggest alternatives or adjustments to their requirements that might yield better results.
                        Your goal is to keep the conversation productive and helpful."""

                        no_results_prompt = f"""
                        The user is looking for plants with these preferences:
                        {json.dumps(conversation['preferences'], indent=2)}

                        Unfortunately, we couldn't find plants that perfectly match all these criteria.

                        Generate a helpful response that:
                        1. Acknowledges their preferences
                        2. Suggests which criteria might be making it difficult to find matches
                        3. Recommends 1-2 adjustments they could make to find more options
                        4. Suggests 2-3 plants that might work if they relaxed certain requirements
                        5. Asks a specific follow-up question to help refine the search

                        Keep your response friendly and educational while demonstrating plant expertise.
                        """

                        openai_response = openai.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": no_results_prompt}
                            ],
                            max_tokens=350,
                            temperature=0.7
                        )

                        no_results_response = openai_response.choices[0].message.content.strip()
                        conversation['messages'].append({"role": "assistant", "content": no_results_response})

                        return {
                            'type': 'text',
                            'content': no_results_response
                        }
                    except Exception as e:
                        logger.error(f"Error generating OpenAI no-results response: {str(e)}")

                # Get some default recommendations based on location only
                mock_plants = get_mock_plants()
                default_resp = "Based on what you're looking for, I'd suggest a few easy-to-care-for plants: "

                if "kitchen" in message_lower:
                    default_resp += "Herbs like Basil, Mint, or Thyme would work well in your kitchen. They're useful for cooking and generally easy to maintain with medium light."
                elif "bathroom" in message_lower:
                    default_resp += "Peace Lily, Spider Plant, or Aloe Vera would thrive in your bathroom. They do well in higher humidity and don't need a lot of light."
                elif "bedroom" in message_lower:
                    default_resp += "Snake Plant, Pothos, or Peace Lily would be perfect for your bedroom. They help purify the air and don't require much maintenance."
                elif "living room" in message_lower:
                    default_resp += "Monstera, Fiddle Leaf Fig, or Pothos would look great in your living room. They make attractive statement plants that aren't too demanding."
                elif "office" in message_lower:
                    default_resp += "Snake Plant, ZZ Plant, or Spider Plant would work well in your office. They tolerate low light and infrequent watering."
                else:
                    default_resp += "Snake Plant, Pothos, or ZZ Plant are generally easy to care for and adapt to most environments. They're perfect if you're just starting out."

                conversation['messages'].append({"role": "assistant", "content": default_resp})

                return {
                    'type': 'text',
                    'content': default_resp
                }

        # If we don't have enough preferences for recommendations, ask clarifying questions
        # ENHANCED: Use more sophisticated follow-up questions
        if openai_api_key:
            try:
                # Get conversation history for better context
                complete_history = [{"role": m["role"], "content": m["content"]} for m in conversation['messages']]

                # Add detailed system message
                system_message = """You are an expert gardener and plant specialist who helps people find the perfect plants.
                Your goal is to ask thoughtful follow-up questions to understand the user's specific needs and preferences.
                Ask ONE specific follow-up question that will be most helpful in finding the right plants.
                Your questions should demonstrate plant knowledge and be conversational in tone.
                Focus on the MOST important missing information for making good plant recommendations.
                """

                # Add a guidance prompt at the end of the conversation
                guidance_prompt = {
                    "role": "user",
                    "content": f"""Based on our conversation so far and these preferences:
                    {json.dumps(conversation['preferences'], indent=2)}

                    What's the SINGLE most important question I should ask next to help them find the perfect plants?
                    Phrase it as a direct question to the user that sounds natural and conversational.
                    Focus especially on missing information about: location, light conditions, maintenance preferences, or specific plant interests.
                    Your question should be friendly and demonstrate your gardening expertise.
                    """
                }

                # Create full message list
                messages = complete_history + [guidance_prompt]

                # Get a contextual follow-up question from OpenAI
                openai_response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "system", "content": system_message}] + messages,
                    max_tokens=150,
                    temperature=0.7
                )

                follow_up_question = openai_response.choices[0].message.content.strip()
                conversation['messages'].append({"role": "assistant", "content": follow_up_question})

                return {
                    'type': 'text',
                    'content': follow_up_question
                }
            except Exception as e:
                logger.error(f"Error generating follow-up question with OpenAI: {str(e)}")

        # Fallback questions if OpenAI fails or isn't available
        response_text = ""

        # Determine what information we need most
        if not has_location:
            response_text = "What room or space would you like to add plants to? For example, kitchen, living room, bedroom, bathroom, office, or balcony?"
        elif 'light' not in conversation['preferences'] or not conversation['preferences']['light']:
            response_text = f"How would you describe the lighting conditions in your {conversation['preferences']['location'].replace('_', ' ')}? Is it low light, medium light, bright indirect light, or direct sunlight?"
        elif 'maintenance' not in conversation['preferences'] or not conversation['preferences']['maintenance']:
            response_text = "How much time can you dedicate to plant care? Would you prefer low-maintenance plants that need attention only every few weeks, medium-maintenance plants requiring weekly care, or are you up for plants that need more frequent attention?"
        else:
            response_text = "Are there any specific features you're looking for in your plants? For example, air-purifying qualities, colorful foliage, flowering plants, or plants that are safe for pets?"

        conversation['messages'].append({"role": "assistant", "content": response_text})
        return {
            'type': 'text',
            'content': response_text
        }

    except Exception as e:
        logger.error(f"Error in process_chat_with_ai: {str(e)}", exc_info=True)
        return {
            'type': 'error',
            'content': "I'm sorry, I encountered an error processing your request. Please try again with a different question about plants or gardening."
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


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)


@app.route('/api/chat', methods=['POST'])
def chat():
    """API endpoint for chat interactions"""
    try:
        data = request.get_json(silent=True) or {}
        logger.info(f"Received chat request: {data}")

        message = data.get('message', '')
        session_id = data.get('session_id', str(uuid.uuid4()))

        # Check if this is a new session with a greeting
        is_greeting = False
        if session_id not in conversations and any(greeting in message.lower() for greeting in
                                                   ['hi', 'hello', 'hey', 'start', 'help', '']):
            is_greeting = True
            # Create a more engaging first greeting with OpenAI if available
            if openai_api_key:
                try:
                    system_message = """You are GrowVRD, an enthusiastic and knowledgeable plant expert. 
                    Create a warm, engaging first greeting that introduces yourself as a plant recommendation assistant.
                    Your greeting should be friendly and encourage the user to tell you about what kind of plants they're looking for.
                    Mention that you can help them find the perfect plants for their specific space and preferences.
                    Keep your greeting under 100 words, conversational, and end with an open question."""

                    greeting_response = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user",
                             "content": "Create an engaging first greeting for a plant recommendation assistant."}
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )

                    greeting_text = greeting_response.choices[0].message.content.strip()

                    # Initialize conversation with this greeting
                    conversations[session_id] = {
                        'messages': [{"role": "assistant", "content": greeting_text}],
                        'preferences': {},
                        'last_update': datetime.now().isoformat()
                    }

                    # Return the greeting directly
                    return jsonify({
                        'type': 'text',
                        'content': greeting_text,
                        'session_id': session_id
                    })
                except Exception as e:
                    logger.error(f"Error generating greeting with OpenAI: {str(e)}")
                    # Fall back to standard greeting if OpenAI fails
                    is_greeting = False

        # Process the message using AI
        response = process_chat_with_ai(message, session_id)

        # Add session ID to response for frontend tracking
        response['session_id'] = session_id

        logger.info(f"Generated response: {response}")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": f"I encountered a problem processing your request. Could you try asking about plants in a different way?",
            "session_id": data.get('session_id', str(uuid.uuid4()))
        })


@app.route('/api/perenual-status')
def perenual_status():
    """Endpoint to verify Perenual API connection"""
    if not PERENUAL_ENABLED:
        return jsonify({
            "status": "error",
            "message": "Perenual API integration not enabled"
        }), 500

    try:
        test_plant = create_test_plant()

        if test_plant:
            return jsonify({
                "status": "success",
                "message": "Perenual API connection successful",
                "plant": test_plant
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to create test plant from Perenual API"
            }), 500
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error testing Perenual API: {error_message}")
        return jsonify({
            "status": "error",
            "message": f"Error testing Perenual API: {error_message}"
        }), 500


# Debug endpoint
@app.route('/api/debug', methods=['GET'])
def debug():
    """Debug endpoint to check conversations and system state"""
    debug_info = {
        "conversations": {},
        "data_stats": {
            "plants_count": len(get_mock_plants()),
            "products_count": len(get_mock_products()),
            "kits_count": len(get_mock_kits()),
            "perenual_enabled": PERENUAL_ENABLED,
            "perenual_cache_size": len(perenual_cache)
        },
        "environment": {
            "openai_key_set": bool(openai_api_key),
            "openai_key_masked": f"{openai_api_key[:3]}...{openai_api_key[-3:]}" if openai_api_key else None,
            "debug_mode": app.debug,
            "server_time": datetime.now().isoformat()
        }
    }

    # Sanitize conversation data for display
    for session_id, convo in conversations.items():
        debug_info["conversations"][session_id] = {
            "message_count": len(convo.get('messages', [])),
            "preferences": convo.get('preferences', {}),
            "last_message": convo.get('messages', [])[-1]["content"] if convo.get('messages', []) else None,
            "last_update": convo.get('last_update')
        }

    return jsonify(debug_info)


# Health check endpoint
@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "perenual_status": "enabled" if PERENUAL_ENABLED else "disabled"
    })


# Advanced debugging - view and clear conversations
@app.route('/api/debug/conversations/<session_id>', methods=['GET'])
def view_conversation(session_id):
    """View conversation details for a specific session"""
    if session_id in conversations:
        # Return full conversation details for debugging
        return jsonify({
            "session_id": session_id,
            "conversation": conversations[session_id]
        })
    else:
        return jsonify({
            "error": "Session not found"
        }), 404


@app.route('/api/debug/conversations/<session_id>', methods=['DELETE'])
def clear_conversation(session_id):
    """Clear a specific conversation"""
    if session_id in conversations:
        del conversations[session_id]
        return jsonify({
            "status": "success",
            "message": f"Conversation {session_id} cleared"
        })
    else:
        return jsonify({
            "error": "Session not found"
        }), 404


@app.route('/api/debug/conversations', methods=['DELETE'])
def clear_all_conversations():
    """Clear all conversations"""
    conversations.clear()
    return jsonify({
        "status": "success",
        "message": "All conversations cleared"
    })


# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting GrowVRD on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)