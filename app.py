#!/usr/bin/env python3
"""
GrowVRD - AWS-Native Flask Application
Full DynamoDB integration with enhanced chat processing
"""

import os
import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('growvrd_app')

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
CORS(app, supports_credentials=True)

# Initialize AWS DynamoDB connector
dynamo_connector = None
try:
    from aws.dynamo_connector import DynamoConnector

    # Configure for your migrated tables
    dynamo_connector = DynamoConnector(
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        table_prefix='growvrd'
    )


    # Override table names to match your actual migrated tables
    def get_full_table_name(table_type: str) -> str:
        table_map = {
            'plants': os.getenv('DYNAMODB_PLANTS_TABLE', 'growvrd-plants-development'),
            'products': os.getenv('DYNAMODB_PRODUCTS_TABLE', 'growvrd-products-development'),
            'users': os.getenv('DYNAMODB_USERS_TABLE', 'growvrd-users-development'),
            'kits': os.getenv('DYNAMODB_KITS_TABLE', 'growvrd-kits-development'),
            'plant_products': os.getenv('DYNAMODB_PLANT_PRODUCTS_TABLE', 'growvrd-plant-products-development'),
            'user_plants': os.getenv('DYNAMODB_USER_PLANTS_TABLE', 'growvrd-user-plants-development'),
            'local_vendors': os.getenv('DYNAMODB_LOCAL_VENDORS_TABLE', 'growvrd-local-vendors-development')
        }
        return table_map.get(table_type, f"growvrd-{table_type}-development")


    dynamo_connector._get_table_name = get_full_table_name
    logger.info("✅ AWS DynamoDB connector initialized")

except Exception as e:
    logger.error(f"❌ DynamoDB initialization failed: {e}")
    dynamo_connector = None

# Initialize enhanced chat system
enhanced_chat_available = False
try:
    from enhanced_chat import enhanced_chat_response

    enhanced_chat_available = True
    logger.info("✅ Enhanced chat system loaded")
except ImportError as e:
    logger.warning(f"Enhanced chat not available: {e}")

# OpenAI for fallback chat
openai_client = None
try:
    from openai import OpenAI

    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    logger.info("✅ OpenAI client initialized")
except Exception as e:
    logger.warning(f"OpenAI not available: {e}")

# Global variables for session management
conversations = {}


def create_aws_plant_expert_prompt():
    """Enhanced system prompt for AWS-powered plant expert"""
    return """You are GrowVRD, an expert plant consultant with access to a comprehensive AWS-powered plant database. You're enthusiastic, knowledgeable, and genuinely excited about helping people succeed with plants.

🌿 YOUR AWS-POWERED EXPERTISE:
- Access to real plant database with detailed care instructions stored in DynamoDB
- Product compatibility ratings (1-5 scale) with detailed warnings and recommendations
- Room condition analysis and plant placement optimization
- Personal plant tracking with nicknames and care history
- Real-time plant health monitoring and troubleshooting

💬 CONVERSATION STYLE:
- Natural, warm, and encouraging (like talking to a plant-loving friend)
- Ask follow-up questions to understand their specific needs
- Reference their existing plants and preferences when known
- Give specific, actionable advice with confidence
- Use emojis naturally to show enthusiasm

🎯 WHEN HELPING:
1. **Listen actively** - understand their space, experience, goals
2. **Recommend specifically** - not just "snake plant" but "snake plant in a terracotta pot near your east window"
3. **Explain why** - share the reasoning behind recommendations
4. **Anticipate needs** - suggest complementary products and future care
5. **Follow up** - ask if they want to know more about specific aspects

📊 USE YOUR AWS DATA:
- When suggesting plants, mention specific care requirements from database
- Include product compatibility warnings (ratings 1-2 = avoid, 4-5 = excellent)
- Reference real Amazon products and local vendor options when relevant
- Provide realistic care schedules based on actual plant needs

Remember: You're not just giving information - you're helping someone build confidence and joy in their plant journey using real, comprehensive data! 🌱"""


def get_user_context_from_dynamo(session_id: str, user_email: str = None) -> Dict[str, Any]:
    """Load user context from DynamoDB"""
    try:
        if not dynamo_connector:
            return {}

        user_context = {
            'session_id': session_id,
            'plants': [],
            'preferences': {},
            'room_conditions': {}
        }

        # If we have user email, load their actual data
        if user_email:
            try:
                user = dynamo_connector.get_user_by_email(user_email)
                if user:
                    user_plants = dynamo_connector.get_user_plants(user.get('id', ''))
                    user_context['plants'] = user_plants
                    user_context['preferences'] = user.get('preferences', {})
                    user_context['room_conditions'] = user.get('room_conditions', {})
            except Exception as e:
                logger.warning(f"Could not load user data: {e}")

        return user_context

    except Exception as e:
        logger.error(f"Error loading user context: {e}")
        return {}


def get_plant_recommendations_from_dynamo(query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Get plant recommendations using DynamoDB data"""
    try:
        if not dynamo_connector:
            return []

        # Get all plants from DynamoDB
        plants = dynamo_connector.get_plants()

        # Basic filtering based on query
        recommendations = []
        query_lower = query.lower()

        for plant in plants:
            plant_name = plant.get('name', '').lower()
            plant_desc = plant.get('description', '').lower()

            # Calculate match score
            match_score = 0

            # Name matching
            if any(word in plant_name for word in query_lower.split()):
                match_score += 30

            # Description matching
            if any(word in plant_desc for word in query_lower.split()):
                match_score += 20

            # Light condition matching
            if 'low light' in query_lower and plant.get('natural_sunlight_needs') == 'low':
                match_score += 25
            elif 'bright' in query_lower and plant.get('natural_sunlight_needs') == 'high':
                match_score += 25

            # Difficulty matching
            if 'easy' in query_lower or 'beginner' in query_lower:
                difficulty = plant.get('difficulty', 5)
                if isinstance(difficulty, (int, float)) and difficulty <= 3:
                    match_score += 20

            # Location matching
            compatible_locations = plant.get('compatible_locations', [])
            if isinstance(compatible_locations, list):
                for location in ['bedroom', 'bathroom', 'kitchen', 'living room']:
                    if location in query_lower and location in ' '.join(compatible_locations).lower():
                        match_score += 15

            # Add match score to plant
            if match_score > 0:
                plant['match_score'] = match_score
                plant['normalized_score'] = min(match_score, 100)
                recommendations.append(plant)

        # Sort by match score and return top results
        recommendations.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        return recommendations[:6]

    except Exception as e:
        logger.error(f"Error getting plant recommendations: {e}")
        return []


def get_compatible_products_from_dynamo(plant_id: str) -> List[Dict[str, Any]]:
    """Get compatible products for a plant using DynamoDB data"""
    try:
        if not dynamo_connector:
            return []

        # Get plant-product relationships
        relationships = dynamo_connector.get_products_for_plant(plant_id)

        compatible_products = []
        for relationship in relationships:
            product_id = relationship.get('product_id')
            compatibility_rating = relationship.get('compatibility_rating', 3)

            if product_id:
                # Get the actual product data
                products = dynamo_connector.get_products()
                product = next((p for p in products if p.get('id') == product_id), None)

                if product:
                    # Add compatibility info to product
                    product['compatibility_rating'] = compatibility_rating
                    product['compatibility_notes'] = relationship.get('compatibility_notes', '')
                    product['primary_purpose'] = relationship.get('primary_purpose', '')

                    # Only include products with rating 3 or higher
                    if compatibility_rating >= 3:
                        compatible_products.append(product)

        # Sort by compatibility rating
        compatible_products.sort(key=lambda x: x.get('compatibility_rating', 0), reverse=True)
        return compatible_products[:4]

    except Exception as e:
        logger.error(f"Error getting compatible products: {e}")
        return []


def process_chat_message_aws(message: str, session_id: str, user_email: str = None) -> Dict[str, Any]:
    """AWS-native chat processing with DynamoDB integration"""
    try:
        # Get or create conversation
        if session_id not in conversations:
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0,
                'user_context': {}
            }

        conversation = conversations[session_id]
        conversation['message_count'] += 1

        # Handle reset commands
        if any(cmd in message.lower() for cmd in ["restart", "reset", "start over", "new conversation"]):
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0,
                'user_context': {}
            }
            return {
                'type': 'text',
                'content': "Perfect! Let's start fresh! 🌿 I'm GrowVRD, your AWS-powered plant expert. I have access to a comprehensive plant database and I'm here to help you create your perfect indoor garden. What are you hoping to grow?",
                'enhanced': True,
                'aws_powered': True
            }

        # Load user context from DynamoDB
        user_context = get_user_context_from_dynamo(session_id, user_email)

        # Use enhanced chat system if available
        if enhanced_chat_available:
            response = enhanced_chat_response(
                message=message,
                conversation_history=conversation['messages'],
                user_context=user_context
            )
        else:
            # Fallback to AWS-native chat processing
            response = process_standard_chat_aws(message, conversation['messages'], user_context)

        # Update conversation history
        conversation['messages'].append({
            'role': 'user',
            'content': message,
            'timestamp': datetime.now().isoformat()
        })

        conversation['messages'].append({
            'role': 'assistant',
            'content': response.get('content', ''),
            'timestamp': datetime.now().isoformat()
        })

        # Keep only last 10 messages for memory management
        if len(conversation['messages']) > 10:
            conversation['messages'] = conversation['messages'][-10:]

        conversation['last_update'] = datetime.now().isoformat()

        return response

    except Exception as e:
        logger.error(f"AWS chat processing error: {str(e)}")
        return {
            'type': 'error',
            'content': "I'm having a quick moment! Let me refocus... What can I help you with regarding plants? 🌱",
            'session_id': session_id,
            'aws_powered': True
        }


def process_standard_chat_aws(message: str, conversation_history: List[Dict], user_context: Dict[str, Any]) -> Dict[
    str, Any]:
    """AWS-native chat processing fallback"""
    try:
        if not openai_client:
            return {
                'type': 'error',
                'content': "Chat system temporarily unavailable. Please try again later.",
                'aws_powered': True
            }

        # Build conversation context
        messages = [{"role": "system", "content": create_aws_plant_expert_prompt()}]

        # Add user context if available
        if user_context.get('plants'):
            plant_names = [plant.get('nickname', plant.get('name', 'Unknown'))
                           for plant in user_context['plants']]
            context_msg = f"User's current plants: {', '.join(plant_names)}"
            messages.append({"role": "system", "content": context_msg})

        # Add conversation history
        for msg in conversation_history[-6:]:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Add current message
        messages.append({"role": "user", "content": message})

        # Generate AI response
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=600,
            temperature=0.7
        )

        ai_content = response.choices[0].message.content

        # Try to get plant recommendations if message seems like a request
        plants = []
        products = []
        if any(keyword in message.lower() for keyword in ['recommend', 'suggest', 'need', 'want', 'looking for']):
            plants = get_plant_recommendations_from_dynamo(message)
            if plants:
                # Get products for the top recommended plant
                top_plant_id = plants[0].get('id')
                if top_plant_id:
                    products = get_compatible_products_from_dynamo(top_plant_id)

        return {
            'type': 'text',
            'content': ai_content,
            'plants': plants,
            'products': products,
            'enhanced': False,
            'aws_powered': True
        }

    except Exception as e:
        logger.error(f"Standard AWS chat processing error: {e}")
        return {
            'type': 'error',
            'content': "I'm having trouble processing your request. Could you try rephrasing your question about plants?",
            'aws_powered': True
        }


@app.route('/')
def index():
    """Main landing page"""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return "<h1>🌿 GrowVRD - Your AWS-Powered Plant Expert</h1><p>Welcome to GrowVRD! <a href='/chat'>Start chatting</a></p>"


@app.route('/chat')
def chat():
    """Chat interface page"""
    try:
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        return render_template('chat.html')
    except Exception as e:
        logger.error(f"Error rendering chat: {e}")
        return "<h1>🌿 GrowVRD Chat</h1><p>Chat interface temporarily unavailable. Please try again later.</p>"


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """AWS-powered chat API endpoint"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        user_email = data.get('user_email')  # Optional user identification

        if not message:
            return jsonify({
                'error': 'Message cannot be empty',
                'type': 'error'
            }), 400

        # Get or create session ID
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id

        # Process the message using AWS
        response = process_chat_message_aws(message, session_id, user_email)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({
            'error': 'Internal server error',
            'type': 'error',
            'content': 'Sorry, I encountered an issue. Please try again!',
            'aws_powered': True
        }), 500


@app.route('/api/plants/recommendations', methods=['POST'])
def get_plant_recommendations():
    """Get plant recommendations from DynamoDB"""
    try:
        data = request.get_json()
        query = data.get('query', '')
        filters = data.get('filters', {})

        # Get recommendations from DynamoDB
        recommendations = get_plant_recommendations_from_dynamo(query, filters)

        return jsonify({
            'recommendations': recommendations,
            'source': 'dynamodb',
            'aws_powered': True
        })

    except Exception as e:
        logger.error(f"Recommendations API error: {e}")
        return jsonify({
            'error': 'Could not get recommendations',
            'aws_powered': True
        }), 500


@app.route('/api/products/compatibility/<plant_id>')
def get_product_compatibility(plant_id):
    """Get compatible products for a specific plant from DynamoDB"""
    try:
        # Get compatible products from DynamoDB
        products = get_compatible_products_from_dynamo(plant_id)

        return jsonify({
            'products': products,
            'plant_id': plant_id,
            'source': 'dynamodb',
            'aws_powered': True
        })

    except Exception as e:
        logger.error(f"Product compatibility API error: {e}")
        return jsonify({
            'error': 'Could not get product compatibility',
            'aws_powered': True
        }), 500


@app.route('/api/kits')
def get_plant_kits():
    """Get available plant kits from DynamoDB"""
    try:
        if dynamo_connector:
            kits = dynamo_connector.get_kits()
        else:
            kits = []

        return jsonify({
            'kits': kits,
            'source': 'dynamodb',
            'aws_powered': True
        })

    except Exception as e:
        logger.error(f"Kits API error: {e}")
        return jsonify({
            'error': 'Could not get plant kits',
            'aws_powered': True
        }), 500


@app.route('/api/user/plants/<user_email>')
def get_user_plants(user_email):
    """Get user's plants from DynamoDB"""
    try:
        if not dynamo_connector:
            return jsonify({'error': 'Database not available'}), 503

        # Get user first
        user = dynamo_connector.get_user_by_email(user_email)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get user's plants
        user_plants = dynamo_connector.get_user_plants(user.get('id', ''))

        return jsonify({
            'plants': user_plants,
            'user_id': user.get('id'),
            'source': 'dynamodb',
            'aws_powered': True
        })

    except Exception as e:
        logger.error(f"User plants API error: {e}")
        return jsonify({
            'error': 'Could not get user plants',
            'aws_powered': True
        }), 500


@app.route('/api/health')
def health_check():
    """AWS-aware health check endpoint"""
    health_status = {
        'status': 'healthy',
        'aws_powered': True,
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0-aws'
    }

    # Check DynamoDB health
    if dynamo_connector:
        try:
            dynamo_health = dynamo_connector.health_check()
            health_status['dynamodb'] = dynamo_health
        except Exception as e:
            health_status['dynamodb'] = {'status': 'unhealthy', 'error': str(e)}
    else:
        health_status['dynamodb'] = {'status': 'not_connected'}

    # Check enhanced chat
    health_status['enhanced_chat'] = enhanced_chat_available

    # Check OpenAI
    health_status['openai'] = openai_client is not None

    return jsonify(health_status)


@app.route('/api/session/reset', methods=['POST'])
def reset_session():
    """Reset user session"""
    try:
        session_id = session.get('session_id')
        if session_id and session_id in conversations:
            del conversations[session_id]

        # Create new session
        new_session_id = str(uuid.uuid4())
        session['session_id'] = new_session_id

        return jsonify({
            'message': 'Session reset successfully',
            'new_session_id': new_session_id,
            'aws_powered': True
        })

    except Exception as e:
        logger.error(f"Session reset error: {e}")
        return jsonify({
            'error': 'Could not reset session',
            'aws_powered': True
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'aws_powered': True
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'aws_powered': True
    }), 500


if __name__ == "__main__":
    # Determine port
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'

    logger.info(f"🌿 Starting GrowVRD AWS-powered application on port {port}")
    logger.info(f"DynamoDB connector: {'✅ Connected' if dynamo_connector else '❌ Not available'}")
    logger.info(f"Enhanced chat: {'✅ Available' if enhanced_chat_available else '❌ Not available'}")
    logger.info(f"OpenAI: {'✅ Available' if openai_client else '❌ Not available'}")

    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=port
    )