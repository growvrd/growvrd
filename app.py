#!/usr/bin/env python3
"""
GrowVRD - OpenAI Optimized Flask Application
Maximum ChatGPT-like experience with DynamoDB integration
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
    logger.info("DynamoDB connector initialized successfully")

except Exception as e:
    logger.error(f"DynamoDB initialization failed: {e}")
    dynamo_connector = None

# Initialize enhanced chat system
enhanced_chat_available = False
try:
    from enhanced_chat import enhanced_chat_response

    enhanced_chat_available = True
    logger.info("Enhanced OpenAI chat system loaded")
except ImportError as e:
    logger.warning(f"Enhanced chat not available: {e}")

# OpenAI for fallback chat
openai_client = None
try:
    from openai import OpenAI

    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    logger.info("OpenAI client initialized")
except Exception as e:
    logger.warning(f"OpenAI not available: {e}")

# Global variables for session management
conversations = {}


def create_plant_expert_prompt():
    """System prompt for plant expert without excessive emojis"""
    return """You are GrowVRD, an expert plant consultant with access to a comprehensive AWS-powered plant database. You're enthusiastic, knowledgeable, and genuinely excited about helping people succeed with plants.

YOUR EXPERTISE:
- Access to real plant database with detailed care instructions stored in DynamoDB
- Product compatibility ratings (1-5 scale) with detailed warnings and recommendations
- Room condition analysis and plant placement optimization
- Personal plant tracking with nicknames and care history
- Real-time plant health monitoring and troubleshooting

CONVERSATION STYLE:
- Natural, warm, and encouraging (like talking to a knowledgeable friend)
- Ask follow-up questions to understand their specific needs
- Reference their existing plants and preferences when known
- Give specific, actionable advice with confidence
- Use emojis naturally but sparingly for warmth

WHEN HELPING:
1. Listen actively - understand their space, experience, goals
2. Recommend specifically - not just "snake plant" but "snake plant in a terracotta pot near your east window"
3. Explain why - share the reasoning behind recommendations
4. Anticipate needs - suggest complementary products and future care
5. Follow up - ask if they want to know more about specific aspects

USE YOUR DATA:
- When suggesting plants, mention specific care requirements from database
- Include product compatibility warnings (ratings 1-2 = avoid, 4-5 = excellent)
- Reference real Amazon products and local vendor options when relevant
- Provide realistic care schedules based on actual plant needs

Remember: You're helping someone build confidence and joy in their plant journey using real, comprehensive data."""


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


def process_chat_message_openai(message: str, session_id: str, user_email: str = None) -> Dict[str, Any]:
    """OpenAI optimized chat processing with DynamoDB integration"""
    try:
        # Get or create conversation
        if session_id not in conversations:
            conversations[session_id] = {
                'messages': [],
                'preferences': {},
                'last_update': datetime.now().isoformat(),
                'message_count': 0,
                'user_context': {},
                'total_tokens_used': 0,
                'conversation_quality_score': 0
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
                'user_context': {},
                'total_tokens_used': 0,
                'conversation_quality_score': 0
            }
            return {
                'type': 'text',
                'content': "Perfect! Let's start fresh. I'm GrowVRD, your plant expert with access to comprehensive plant data. I'm here to help you create your perfect indoor garden with personalized recommendations. What are you hoping to grow?",
                'enhanced': True,
                'openai_powered': True,
                'conversation_reset': True
            }

        # Load comprehensive user context from DynamoDB
        user_context = get_user_context_from_dynamo(session_id, user_email)

        # Add conversation analytics to user context
        user_context['conversation_stats'] = {
            'message_count': conversation['message_count'],
            'total_tokens_used': conversation.get('total_tokens_used', 0),
            'session_duration': (datetime.now() - datetime.fromisoformat(
                conversation['last_update'])).total_seconds() if conversation.get('last_update') else 0
        }

        # Use enhanced OpenAI chat system
        if enhanced_chat_available:
            response = enhanced_chat_response(
                message=message,
                conversation_history=conversation['messages'],
                user_context=user_context
            )

            # Track token usage and conversation quality
            if response.get('tokens_used'):
                conversation['total_tokens_used'] = conversation.get('total_tokens_used', 0) + response['tokens_used']

            # Calculate conversation quality score
            quality_factors = []
            if response.get('plants'):
                quality_factors.append(10)  # Provided plant recommendations
            if response.get('products'):
                quality_factors.append(10)  # Provided product suggestions
            if response.get('intent', {}).get('confidence', 0) > 0.8:
                quality_factors.append(10)  # High confidence in understanding intent
            if len(response.get('content', '')) > 200:
                quality_factors.append(5)  # Detailed response

            conversation['conversation_quality_score'] = sum(quality_factors)

        else:
            # Fallback to standard processing
            response = process_standard_chat_openai(message, conversation['messages'], user_context)

        # Enhanced conversation history tracking
        conversation['messages'].append({
            'role': 'user',
            'content': message,
            'timestamp': datetime.now().isoformat(),
            'intent': response.get('intent', {}),
            'character_count': len(message)
        })

        conversation['messages'].append({
            'role': 'assistant',
            'content': response.get('content', ''),
            'timestamp': datetime.now().isoformat(),
            'provider': response.get('provider', 'unknown'),
            'tokens_used': response.get('tokens_used', 0),
            'plants_provided': len(response.get('plants', [])),
            'products_provided': len(response.get('products', [])),
            'character_count': len(response.get('content', ''))
        })

        # Intelligent conversation history management
        # Keep more history for high-quality conversations
        max_history = 16 if conversation['conversation_quality_score'] > 30 else 10
        if len(conversation['messages']) > max_history:
            conversation['messages'] = conversation['messages'][-max_history:]

        conversation['last_update'] = datetime.now().isoformat()

        # Add performance metrics to response
        response['performance_metrics'] = {
            'session_message_count': conversation['message_count'],
            'total_tokens_used': conversation.get('total_tokens_used', 0),
            'conversation_quality_score': conversation.get('conversation_quality_score', 0),
            'response_time': datetime.now().isoformat()
        }

        return response

    except Exception as e:
        logger.error(f"OpenAI chat processing error: {str(e)}")
        return {
            'type': 'error',
            'content': "I'm having a technical moment! Let me refocus... What specific plant question can I help you with?",
            'session_id': session_id,
            'openai_powered': True,
            'error_details': str(e) if os.getenv('FLASK_ENV') == 'development' else None
        }


def process_standard_chat_openai(message: str, conversation_history: List[Dict], user_context: Dict[str, Any]) -> Dict[
    str, Any]:
    """Standard OpenAI chat processing fallback"""
    try:
        if not openai_client:
            return {
                'type': 'error',
                'content': "Chat system temporarily unavailable. Please try again later.",
                'openai_powered': True
            }

        # Build conversation context
        messages = [{"role": "system", "content": create_plant_expert_prompt()}]

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
            'openai_powered': True,
            'tokens_used': response.usage.total_tokens if hasattr(response, 'usage') else None
        }

    except Exception as e:
        logger.error(f"Standard OpenAI chat processing error: {e}")
        return {
            'type': 'error',
            'content': "I'm having trouble processing your request. Could you try rephrasing your question about plants?",
            'openai_powered': True
        }


@app.route('/')
def index():
    """Main landing page"""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return "<h1>GrowVRD - Your Plant Expert</h1><p>Welcome to GrowVRD! <a href='/chat'>Start chatting</a></p>"


@app.route('/chat')
def chat():
    """Chat interface page"""
    try:
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        return render_template('chat.html')
    except Exception as e:
        logger.error(f"Error rendering chat: {e}")
        return "<h1>GrowVRD Chat</h1><p>Chat interface temporarily unavailable. Please try again later.</p>"


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """OpenAI-powered chat API endpoint"""
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

        # Process the message using OpenAI
        response = process_chat_message_openai(message, session_id, user_email)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({
            'error': 'Internal server error',
            'type': 'error',
            'content': 'Sorry, I encountered an issue. Please try again!',
            'openai_powered': True
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
            'openai_powered': True
        })

    except Exception as e:
        logger.error(f"Recommendations API error: {e}")
        return jsonify({
            'error': 'Could not get recommendations',
            'openai_powered': True
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
            'openai_powered': True
        })

    except Exception as e:
        logger.error(f"Product compatibility API error: {e}")
        return jsonify({
            'error': 'Could not get product compatibility',
            'openai_powered': True
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
            'openai_powered': True
        })

    except Exception as e:
        logger.error(f"Kits API error: {e}")
        return jsonify({
            'error': 'Could not get plant kits',
            'openai_powered': True
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
            'openai_powered': True
        })

    except Exception as e:
        logger.error(f"User plants API error: {e}")
        return jsonify({
            'error': 'Could not get user plants',
            'openai_powered': True
        }), 500


@app.route('/api/analytics/conversation/<session_id>')
def get_conversation_analytics(session_id):
    """Get detailed conversation analytics for OpenAI optimization"""
    try:
        if session_id not in conversations:
            return jsonify({'error': 'Session not found'}), 404

        conversation = conversations[session_id]

        # Calculate detailed analytics
        analytics = {
            'session_id': session_id,
            'message_count': conversation.get('message_count', 0),
            'total_tokens_used': conversation.get('total_tokens_used', 0),
            'conversation_quality_score': conversation.get('conversation_quality_score', 0),
            'duration_minutes': 0,
            'avg_response_length': 0,
            'plant_recommendations_given': 0,
            'product_suggestions_given': 0,
            'openai_performance': {}
        }

        # Analyze messages
        messages = conversation.get('messages', [])
        if messages:
            # Calculate duration
            start_time = datetime.fromisoformat(messages[0]['timestamp'])
            end_time = datetime.fromisoformat(messages[-1]['timestamp'])
            analytics['duration_minutes'] = (end_time - start_time).total_seconds() / 60

            # Analyze assistant messages
            assistant_messages = [m for m in messages if m.get('role') == 'assistant']
            if assistant_messages:
                total_length = sum(m.get('character_count', 0) for m in assistant_messages)
                analytics['avg_response_length'] = total_length / len(assistant_messages)

                analytics['plant_recommendations_given'] = sum(m.get('plants_provided', 0) for m in assistant_messages)
                analytics['product_suggestions_given'] = sum(m.get('products_provided', 0) for m in assistant_messages)

                # Token usage stats
                total_tokens = sum(m.get('tokens_used', 0) for m in assistant_messages)
                analytics['openai_performance'] = {
                    'total_tokens': total_tokens,
                    'avg_tokens_per_response': total_tokens / len(assistant_messages) if assistant_messages else 0,
                    'estimated_cost_usd': total_tokens * 0.0015 / 1000  # Rough estimate for GPT-3.5-turbo
                }

        return jsonify({
            'analytics': analytics,
            'openai_powered': True,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({
            'error': 'Could not generate analytics',
            'openai_powered': True
        }), 500


@app.route('/api/health')
def health_check():
    """Enhanced health check with OpenAI status"""
    health_status = {
        'status': 'healthy',
        'openai_powered': True,
        'timestamp': datetime.now().isoformat(),
        'version': '2.1.0-openai-optimized'
    }

    # Check OpenAI status
    try:
        if enhanced_chat_available:
            from enhanced_chat import openai_client
            if openai_client:
                # Quick test call to verify OpenAI is working
                test_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5
                )
                health_status['openai'] = {
                    'status': 'connected',
                    'model': 'gpt-3.5-turbo',
                    'test_tokens': test_response.usage.total_tokens if hasattr(test_response, 'usage') else 'unknown'
                }
            else:
                health_status['openai'] = {'status': 'client_not_initialized'}
        else:
            health_status['openai'] = {'status': 'enhanced_chat_not_available'}
    except Exception as e:
        health_status['openai'] = {'status': 'error', 'error': str(e)}

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

    # Overall status
    openai_ok = health_status.get('openai', {}).get('status') == 'connected'
    dynamo_ok = health_status.get('dynamodb', {}).get('connection') == 'healthy'

    if openai_ok and dynamo_ok:
        health_status['overall_status'] = 'fully_operational'
    elif openai_ok or dynamo_ok:
        health_status['overall_status'] = 'partially_operational'
    else:
        health_status['overall_status'] = 'degraded'
        health_status['status'] = 'degraded'

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
            'openai_powered': True
        })

    except Exception as e:
        logger.error(f"Session reset error: {e}")
        return jsonify({
            'error': 'Could not reset session',
            'openai_powered': True
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'openai_powered': True
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'openai_powered': True
    }), 500


if __name__ == "__main__":
    # Pre-flight checks for optimal OpenAI performance
    print("Starting GrowVRD with OpenAI optimization...")
    print("=" * 50)

    # Check OpenAI API key
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        print("✓ OpenAI API key found")
        if enhanced_chat_available:
            print("✓ Enhanced OpenAI chat system loaded")

            # Test OpenAI connection
            try:
                from enhanced_chat import openai_client

                if openai_client:
                    # Quick test
                    test_response = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": "Hello"}],
                        max_tokens=5
                    )
                    print(f"✓ OpenAI connection verified ({test_response.usage.total_tokens} tokens)")
                else:
                    print("✗ OpenAI client not initialized")
            except Exception as e:
                print(f"✗ OpenAI connection failed: {e}")
                print("  Check your API key and billing at https://platform.openai.com/")
        else:
            print("✗ Enhanced chat system not available")
    else:
        print("✗ OpenAI API key not found")
        print("  Add OPENAI_API_KEY to your .env file")

    # Check DynamoDB
    if dynamo_connector:
        try:
            health = dynamo_connector.health_check()
            if health.get('connection') == 'healthy':
                print("✓ DynamoDB connected successfully")

                # Show table status
                tables = health.get('tables', {})
                for table_name, status in tables.items():
                    if status.get('status') == 'ACTIVE':
                        item_count = status.get('item_count', 0)
                        print(f"  - {table_name}: {item_count} items")
                    else:
                        print(f"  - {table_name}: {status.get('status', 'ERROR')}")
            else:
                print("✗ DynamoDB connection issues")
        except Exception as e:
            print(f"✗ DynamoDB error: {e}")
    else:
        print("✗ DynamoDB connector not available")

    # Performance status
    print("\nPerformance Status:")
    if openai_key and dynamo_connector and enhanced_chat_available:
        print("✓ OPTIMAL: Full OpenAI + DynamoDB integration")
        print("  Maximum ChatGPT-like experience enabled")
    elif openai_key and enhanced_chat_available:
        print("~ GOOD: OpenAI enabled, DynamoDB limited")
    elif dynamo_connector:
        print("~ LIMITED: DynamoDB only, no AI enhancement")
    else:
        print("✗ BASIC: Fallback mode only")

    print("=" * 50)

    # Determine port and start
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'

    logger.info(f"Starting GrowVRD application on port {port}")

    try:
        app.run(
            debug=debug_mode,
            host='0.0.0.0',
            port=port
        )
    except Exception as e:
        print(f"\nFailed to start application: {e}")
        print("Common fixes:")
        print("  - Check if port is already in use")
        print("  - Verify .env file exists with correct variables")
        print("  - Ensure all dependencies are installed")