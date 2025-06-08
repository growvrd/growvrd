#!/usr/bin/env python3
"""
Enhanced Chat System for GrowVRD
Provides advanced chat capabilities with AWS DynamoDB integration
"""

import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger('enhanced_chat')

# Try to import AWS components
try:
    from aws.dynamo_connector import DynamoConnector

    dynamo_connector = DynamoConnector()
    logger.info("✅ DynamoDB connector loaded")
except ImportError as e:
    dynamo_connector = None
    logger.warning(f"DynamoDB connector not available: {e}")

# Import core data systems
try:
    from core.mock_data import get_mock_plants, get_mock_products
    from core.recommendation_engine import RecommendationEngine
    from core.filters import PlantFilter

    # Initialize core components
    recommendation_engine = RecommendationEngine()
    plant_filter = PlantFilter()
    logger.info("✅ Core recommendation systems loaded")

except ImportError as e:
    recommendation_engine = None
    plant_filter = None
    logger.warning(f"Core systems not available: {e}")

# OpenAI configuration
openai.api_key = os.getenv('OPENAI_API_KEY')


def enhanced_chat_response(
        message: str,
        conversation_history: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate enhanced chat response with data integration

    Args:
        message: User's message
        conversation_history: Previous conversation messages
        user_context: User's personal data and preferences

    Returns:
        Enhanced response with plant recommendations and data
    """
    try:
        # Build enhanced system prompt with user context
        system_prompt = create_context_aware_prompt(user_context or {})

        # Build conversation messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 8 messages to maintain context)
        for msg in conversation_history[-8:]:
            messages.append({
                "role": msg.get('role', 'user'),
                "content": msg.get('content', '')
            })

        # Add current message
        messages.append({"role": "user", "content": message})

        # Generate AI response
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=600,
            temperature=0.7
        )

        ai_content = response.choices[0].message.content

        # Enhance response with data if available
        enhanced_data = enhance_response_with_data(message, user_context or {})

        return {
            'type': 'text',
            'content': ai_content,
            'plants': enhanced_data.get('plants', []),
            'products': enhanced_data.get('products', []),
            'enhanced': True,
            'data_enhanced': bool(enhanced_data.get('plants') or enhanced_data.get('products')),
            'user_context_used': bool(user_context),
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Enhanced chat response error: {e}")
        return {
            'type': 'error',
            'content': "I'm having a moment of confusion! Let me refocus... What can I help you with in your plant journey? 🌱",
            'enhanced': True,
            'error': str(e)
        }


def create_context_aware_prompt(user_context: Dict[str, Any]) -> str:
    """Create system prompt enhanced with user context"""

    base_prompt = """You are GrowVRD, an expert plant consultant with 20+ years of experience. You're enthusiastic, knowledgeable, and genuinely care about helping people succeed with plants.

🌿 YOUR EXPERTISE:
- Comprehensive plant database with detailed care instructions
- Product compatibility knowledge (warn about incompatible products)
- Room condition analysis and optimal placement
- Personal plant health tracking and care history
- Troubleshooting plant problems with specific solutions

💬 CONVERSATION STYLE:
- Warm, encouraging, and natural (like a knowledgeable friend)
- Ask follow-up questions to understand specific needs
- Give specific, actionable advice with confidence
- Use emojis naturally to show enthusiasm
- Reference user's existing plants when relevant

🎯 WHEN HELPING:
1. **Listen actively** - understand their space, experience, and goals
2. **Recommend specifically** - not just "snake plant" but "snake plant in a ceramic pot near your east window"
3. **Explain why** - share reasoning behind recommendations
4. **Anticipate needs** - suggest care products and future considerations
5. **Follow up** - ask if they want to know more about specific aspects

"""

    # Add user context if available
    if user_context:
        context_additions = []

        if user_context.get('plants'):
            plant_names = [plant.get('nickname', plant.get('name', 'Unknown'))
                           for plant in user_context['plants']]
            context_additions.append(f"👤 USER'S CURRENT PLANTS: {', '.join(plant_names)}")

        if user_context.get('preferences'):
            prefs = user_context['preferences']
            if prefs.get('experience_level'):
                context_additions.append(f"👤 EXPERIENCE LEVEL: {prefs['experience_level']}")
            if prefs.get('care_style'):
                context_additions.append(f"👤 CARE STYLE: {prefs['care_style']}")

        if user_context.get('room_conditions'):
            rooms = list(user_context['room_conditions'].keys())
            context_additions.append(f"👤 AVAILABLE SPACES: {', '.join(rooms)}")

        if context_additions:
            base_prompt += "\n" + "\n".join(context_additions) + "\n"

    base_prompt += """
Remember: You're helping someone build confidence and joy in their plant journey. Be the encouraging expert they need! 🌱"""

    return base_prompt


def enhance_response_with_data(message: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance response with relevant plant and product data"""
    enhanced_data = {
        'plants': [],
        'products': []
    }

    try:
        # Check if this seems like a plant recommendation request
        recommendation_keywords = [
            'recommend', 'suggest', 'need', 'want', 'looking for',
            'best plant', 'good plant', 'plant for', 'help me find'
        ]

        is_recommendation_request = any(keyword in message.lower() for keyword in recommendation_keywords)

        if is_recommendation_request and recommendation_engine and plant_filter:
            # Get plant recommendations
            plants = get_plant_recommendations_with_data(message, user_context)
            enhanced_data['plants'] = plants[:3]  # Top 3 recommendations

            # Get compatible products for recommended plants
            if plants:
                for plant in plants[:1]:  # Products for top plant only
                    plant_id = plant.get('id', plant.get('plant_id'))
                    if plant_id:
                        products = get_compatible_products(plant_id)
                        enhanced_data['products'].extend(products[:2])  # Top 2 products per plant

        return enhanced_data

    except Exception as e:
        logger.warning(f"Could not enhance response with data: {e}")
        return enhanced_data


def get_plant_recommendations_with_data(query: str, user_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get plant recommendations using available data sources"""
    try:
        # Try DynamoDB first if available
        if dynamo_connector:
            try:
                # This would be implemented when DynamoDB is fully set up
                plants = dynamo_connector.query_plants_by_criteria(query, user_context)
                if plants:
                    return plants
            except Exception as e:
                logger.warning(f"DynamoDB query failed, falling back to mock data: {e}")

        # Fallback to mock data with filtering
        plants = get_mock_plants()

        if plant_filter:
            # Create filter criteria from query and user context
            filter_criteria = extract_filter_criteria(query, user_context)
            filtered_plants = plant_filter.filter_plants(plants, filter_criteria)

            if recommendation_engine:
                # Score and rank the filtered plants
                recommendations = recommendation_engine.get_recommendations(
                    filtered_plants,
                    {'query': query, 'user_context': user_context}
                )
                return recommendations[:6]  # Top 6
            else:
                return filtered_plants[:6]

        return plants[:6]  # Default top 6

    except Exception as e:
        logger.error(f"Error getting plant recommendations: {e}")
        return []


def get_compatible_products(plant_id: str) -> List[Dict[str, Any]]:
    """Get products compatible with a specific plant"""
    try:
        # Try DynamoDB first if available
        if dynamo_connector:
            try:
                # This would be implemented when DynamoDB is fully set up
                products = dynamo_connector.get_plant_compatible_products(plant_id)
                if products:
                    return products
            except Exception as e:
                logger.warning(f"DynamoDB product query failed, falling back to mock data: {e}")

        # Fallback to mock products
        products = get_mock_products()

        # Filter products that would be good for this plant
        # This is simplified - in real implementation, use compatibility matrix
        compatible_products = []
        for product in products:
            if is_product_compatible(plant_id, product):
                compatible_products.append(product)

        return compatible_products[:4]  # Top 4 compatible products

    except Exception as e:
        logger.error(f"Error getting compatible products: {e}")
        return []


def extract_filter_criteria(query: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract filtering criteria from query and user context"""
    criteria = {}

    query_lower = query.lower()

    # Light requirements
    if any(word in query_lower for word in ['low light', 'dark', 'shade', 'no sun']):
        criteria['sunlight_needs'] = 'low'
    elif any(word in query_lower for word in ['bright', 'sunny', 'sun', 'light']):
        criteria['sunlight_needs'] = 'high'
    elif any(word in query_lower for word in ['medium', 'indirect', 'partial']):
        criteria['sunlight_needs'] = 'medium'

    # Maintenance level
    if any(word in query_lower for word in ['easy', 'low maintenance', 'beginner', 'simple']):
        criteria['maintenance'] = 'low'
    elif any(word in query_lower for word in ['advanced', 'challenging', 'high maintenance']):
        criteria['maintenance'] = 'high'

    # Room/location
    if any(word in query_lower for word in ['bedroom', 'bathroom', 'kitchen', 'living room', 'office']):
        for room in ['bedroom', 'bathroom', 'kitchen', 'living room', 'office']:
            if room in query_lower:
                criteria['location'] = room
                break

    # Size preferences
    if any(word in query_lower for word in ['small', 'tiny', 'mini']):
        criteria['size'] = 'small'
    elif any(word in query_lower for word in ['large', 'big', 'tall']):
        criteria['size'] = 'large'

    # Add user context preferences
    if user_context.get('preferences'):
        prefs = user_context['preferences']
        if prefs.get('experience_level') and 'maintenance' not in criteria:
            if prefs['experience_level'] == 'beginner':
                criteria['maintenance'] = 'low'
            elif prefs['experience_level'] == 'advanced':
                criteria['maintenance'] = 'high'

    return criteria


def is_product_compatible(plant_id: str, product: Dict[str, Any]) -> bool:
    """Simple compatibility check - would use compatibility matrix in real implementation"""
    try:
        # This is a simplified compatibility check
        # In real implementation, this would query the plant-product compatibility matrix

        product_type = product.get('category', '').lower()
        product_name = product.get('name', '').lower()

        # Basic compatibility rules (simplified)
        always_compatible = ['pot', 'soil', 'fertilizer', 'watering']

        return any(compat in product_type for compat in always_compatible) or \
            any(compat in product_name for compat in always_compatible)

    except Exception as e:
        logger.warning(f"Error checking product compatibility: {e}")
        return True  # Default to compatible if we can't determine


# Export the main functions
__all__ = [
    'enhanced_chat_response',
    'get_plant_recommendations_with_data',
    'get_compatible_products',
    'dynamo_connector'
]