#!/usr/bin/env python3
"""
GrowVRD - Optimized Plant Expert Application
Flask app with concise, warm AI responses powered by OpenAI
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import Flask, request, jsonify, session, render_template
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-in-production')

# OpenAI client initialization
openai_client = None
try:
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    logger.info("✅ OpenAI client initialized")
except Exception as e:
    logger.error(f"❌ OpenAI initialization failed: {e}")

# DynamoDB connector
dynamo_connector = None
try:
    from aws.dynamo_connector import DynamoDBConnector

    dynamo_connector = DynamoDBConnector()
    logger.info("✅ DynamoDB connector initialized")
except Exception as e:
    logger.warning(f"⚠️ DynamoDB not available: {e}")

# Enhanced chat system
enhanced_chat_available = False
try:
    from enhanced_chat import enhanced_chat_response

    enhanced_chat_available = True
    logger.info("✅ Enhanced chat system loaded")
except ImportError as e:
    logger.warning(f"⚠️ Enhanced chat not available: {e}")

# Global conversation storage
conversations = {}


def create_concise_expert_prompt() -> str:
    """Create system prompt for warm, concise plant expert"""
    return """You are GrowVRD, a trusted plant expert who gives perfect advice in just 2-3 sentences. You're warm, encouraging, and genuinely excited about helping people succeed with plants.

🎯 YOUR STYLE:
- Maximum 2-3 sentences per response
- Warm, friendly tone like talking to a plant-loving friend
- Give specific, actionable advice
- Use 1-2 emojis naturally for warmth
- Ask ONE follow-up question when helpful

🌱 YOUR EXPERTISE:
- Plant database with detailed care instructions
- Product compatibility ratings (1-5 scale, warn about low ratings)
- Personal plant tracking and health monitoring
- Room-specific placement recommendations

💚 APPROACH:
- Listen to their specific situation first
- Recommend exactly what they need (not generic advice)
- Briefly explain WHY for confidence
- Reference their existing plants when relevant
- Always end with encouragement or curiosity

Remember: You're building plant confidence and joy with every response! 🌿"""


def get_user_context_from_dynamo(session_id: str, user_email: str = None) -> Dict[str, Any]:
    """Get comprehensive user context from DynamoDB"""
    context = {
        'plants': [],
        'preferences': {},
        'room_conditions': {},
        'session_id': session_id
    }

    try:
        if dynamo_connector and user_email:
            # Get user's plants
            user_plants = dynamo_connector.get_user_plants(user_email)
            context['plants'] = user_plants

            # Get user preferences
            user_data = dynamo_connector.get_user_by_email(user_email)
            if user_data:
                context['preferences'] = user_data.get('preferences', {})
                context['room_conditions'] = user_data.get('room_conditions', {})

    except Exception as e:
        logger.error(f"Error getting user context: {e}")

    return context


def get_plant_recommendations_from_dynamo(query: str) -> List[Dict[str, Any]]:
    """Get plant recommendations from DynamoDB with simple scoring"""
    try:
        if not dynamo_connector:
            return []

        plants = dynamo_connector.get_plants()
        recommendations = []
        query_lower = query.lower()

        for plant in plants:
            score = 0
            plant_name = plant.get('name', '').lower()
            plant_desc = plant.get('description', '').lower()
            difficulty = plant.get('difficulty', 5)

            # Simple scoring based on query keywords
            if 'easy' in query_lower or 'beginner' in query_lower:
                if difficulty <= 3:
                    score += 3

            if 'low light' in query_lower or 'dark' in query_lower:
                if 'low light' in plant_desc:
                    score += 3

            if 'small' in query_lower:
                if plant.get('max_height_inches', 100) < 24:
                    score += 2

            if score > 0 or any(word in plant_name for word in query_lower.split()):
                plant['recommendation_score'] = score
                recommendations.append(plant)

        # Sort by score and return top 5
        recommendations.sort(key=lambda x: x.get('recommendation_score', 0), reverse=True)
        return recommendations[:5]

    except Exception as e:
        logger.error(f"Error getting plant recommendations: {e}")
        return []


def get_compatible_products_from_dynamo(plant_id: str) -> List[Dict[str, Any]]:
    """Get compatible products from DynamoDB"""
    try:
        if not dynamo_connector:
            return []

        products = dynamo_connector.get_products()
        compatible_products = []

        # Simple compatibility check (expand based on your relationship data)
        for product in products:
            rating = product.get('compatibility_rating', 3)
            if rating >= 3:  # Only show compatible products
                product_copy = product.copy()
                product_copy['compatibility_rating'] = rating

                # Add recommendation text based on rating
                if rating >= 5:
                    product_copy['recommendation_text'] = "Perfect match!"
                elif rating >= 4:
                    product_copy['recommendation_text'] = "Excellent choice"
                else:
                    product_copy['recommendation_text'] = "Good option"

                compatible_products.append(product_copy)

        # Sort by rating
        compatible_products.sort(key=lambda x: x.get('compatibility_rating', 0), reverse=True)
        return compatible_products[:4]

    except Exception as e:
        logger.error(f"Error getting compatible products: {e}")
        return []


def process_chat_message_optimized(message: str, session_id: str, user_email: str = None) -> Dict[str, Any]:
    """Process chat with optimized concise responses"""
    try:
        # Get or create conversation
        if session_id not in conversations:
            conversations[session_id] = {
                'messages': [],
                'last_update': datetime.now().isoformat(),
                'message_count': 0,
                'user_context': {},
                'total_tokens_used': 0
            }

        conversation = conversations[session_id]
        conversation['message_count'] += 1

        # Handle reset commands
        if any(cmd in message.lower() for cmd in ["restart", "reset", "start over"]):
            conversations[session_id] = {
                'messages': [],
                'last_update': datetime.now().isoformat(),
                'message_count': 0,
                'user_context': {},
                'total_tokens_used': 0
            }
            return {
                'type': 'text',
                'content': "Fresh start! 🌱 I'm GrowVRD, your plant expert. What would you like to grow?",
                'session_id': session_id,
                'enhanced': True,
                'conversation_reset': True
            }

        # Get user context
        user_context = get_user_context_from_dynamo(session_id, user_email)

        # Use enhanced chat if available
        if enhanced_chat_available:
            response = enhanced_chat_response(
                message=message,
                conversation_history=conversation['messages'],
                user_context=user_context
            )

            # Track token usage
            if response.get('tokens_used'):
                conversation['total_tokens_used'] += response['tokens_used']

        else:
            # Fallback to standard OpenAI processing
            response = process_standard_chat_optimized(message, conversation['messages'], user_context)

        # Update conversation history
        conversation['messages'].append({
            'role': 'user',
            'content': message,
            'timestamp': datetime.now().isoformat()
        })

        conversation['messages'].append({
            'role': 'assistant',
            'content': response.get('content', ''),
            'timestamp': datetime.now().isoformat(),
            'tokens_used': response.get('tokens_used', 0),
            'plants_provided': len(response.get('plants', [])),
            'products_provided': len(response.get('products', []))
        })

        # Keep conversation history manageable
        if len(conversation['messages']) > 20:
            conversation['messages'] = conversation['messages'][-20:]

        conversation['last_update'] = datetime.now().isoformat()

        # Add session info to response
        response['session_id'] = session_id
        response['message_count'] = conversation['message_count']

        return response

    except Exception as e:
        logger.error(f"Chat processing error: {e}")
        return {
            'type': 'error',
            'content': "Quick hiccup! What plant question can I help you with? 🌱",
            'session_id': session_id,
            'enhanced': True,
            'error_details': str(e) if app.debug else None
        }


def process_standard_chat_optimized(message: str, conversation_history: List[Dict], user_context: Dict[str, Any]) -> \
Dict[str, Any]:
    """Standard OpenAI chat with concise optimization"""
    try:
        if not openai_client:
            return {
                'type': 'error',
                'content': "Chat temporarily unavailable. Try again in a moment! 🌿",
                'enhanced': False
            }

        # Build conversation
        messages = [{"role": "system", "content": create_concise_expert_prompt()}]

        # Add user context
        if user_context.get('plants'):
            plant_names = [p.get('nickname', p.get('name', 'Unknown')) for p in user_context['plants']]
            context_msg = f"User's plants: {', '.join(plant_names[:3])}"
            messages.append({"role": "system", "content": context_msg})

        # Add recent conversation history (keep it short)
        for msg in conversation_history[-4:]:
            if len(msg.get('content', '')) < 150:  # Skip very long messages
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })

        # Add current message
        messages.append({"role": "user", "content": message})

        # Generate concise response
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=120,  # Perfect for 2-3 sentences
            temperature=0.8,  # Slightly warmer for friendliness
            presence_penalty=0.2,
            frequency_penalty=0.3
        )

        ai_content = response.choices[0].message.content

        # Get recommendations if message seems like a request
        plants = []
        products = []
        if any(keyword in message.lower() for keyword in ['recommend', 'suggest', 'need', 'want', 'looking for']):
            plants = get_plant_recommendations_from_dynamo(message)[:3]
            if plants:
                top_plant_id = plants[0].get('id')
                if top_plant_id:
                    products = get_compatible_products_from_dynamo(top_plant_id)[:2]

        return {
            'type': 'text',
            'content': ai_content,
            'plants': plants,
            'products': products,
            'enhanced': False,
            'provider': 'openai_standard',
            'tokens_used': response.usage.total_tokens if hasattr(response, 'usage') else None
        }

    except Exception as e:
        logger.error(f"Standard chat error: {e}")
        return {
            'type': 'error',
            'content': "Let me refocus... What plant question can I help with? 💚"
        }


# Routes
@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/chat')
def chat():
    """Chat interface"""
    return render_template('chat.html')


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Main chat API endpoint"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()

        if not message:
            return jsonify({
                'error': 'Message is required',
                'content': 'What would you like to know about plants? 🌱'
            }), 400

        # Get or create session
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id

        user_email = data.get('user_email')  # Optional user identification

        # Process message
        response = process_chat_message_optimized(message, session_id, user_email)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({
            'type': 'error',
            'content': 'Quick technical hiccup! What plant question can I help with? 🌿',
            'error': str(e) if app.debug else None
        }), 500


@app.route('/api/recommendations', methods=['POST'])
def api_recommendations():
    """Get plant recommendations"""
    try:
        data = request.get_json()
        query = data.get('query', '')

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Get recommendations
        plants = get_plant_recommendations_from_dynamo(query)

        return jsonify({
            'plants': plants,
            'query': query,
            'count': len(plants),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Recommendations API error: {e}")
        return jsonify({'error': 'Could not get recommendations'}), 500


@app.route('/api/plants/<plant_id>', methods=['GET'])
def api_plant_detail(plant_id):
    """Get specific plant details"""
    try:
        if dynamo_connector:
            plant = dynamo_connector.get_plant_by_id(plant_id)
            if plant:
                return jsonify(plant)

        return jsonify({'error': 'Plant not found'}), 404

    except Exception as e:
        logger.error(f"Plant detail API error: {e}")
        return jsonify({'error': 'Could not get plant details'}), 500


@app.route('/api/products/compatible/<plant_id>', methods=['GET'])
def api_compatible_products(plant_id):
    """Get compatible products for a plant"""
    try:
        products = get_compatible_products_from_dynamo(plant_id)

        return jsonify({
            'products': products,
            'plant_id': plant_id,
            'count': len(products),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Compatible products API error: {e}")
        return jsonify({'error': 'Could not get compatible products'}), 500


@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0-concise-optimized'
    }

    # Check OpenAI
    try:
        if openai_client:
            # Quick test
            test_response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            health_status['openai'] = {
                'status': 'connected',
                'test_tokens': test_response.usage.total_tokens if hasattr(test_response, 'usage') else 'unknown'
            }
        else:
            health_status['openai'] = {'status': 'not_initialized'}
    except Exception as e:
        health_status['openai'] = {'status': 'error', 'error': str(e)}

    # Check DynamoDB
    if dynamo_connector:
        try:
            dynamo_health = dynamo_connector.health_check()
            health_status['dynamodb'] = dynamo_health
        except Exception as e:
            health_status['dynamodb'] = {'status': 'error', 'error': str(e)}
    else:
        health_status['dynamodb'] = {'status': 'not_connected'}

    # Check enhanced chat
    health_status['enhanced_chat'] = enhanced_chat_available

    # Overall status
    openai_ok = health_status.get('openai', {}).get('status') == 'connected'
    if openai_ok and enhanced_chat_available:
        health_status['overall_status'] = 'fully_operational'
    elif openai_ok:
        health_status['overall_status'] = 'basic_operational'
    else:
        health_status['overall_status'] = 'degraded'
        health_status['status'] = 'degraded'

    return jsonify(health_status)


@app.route('/api/session/reset', methods=['POST'])
def api_reset_session():
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
            'new_session_id': new_session_id
        })

    except Exception as e:
        logger.error(f"Session reset error: {e}")
        return jsonify({'error': 'Could not reset session'}), 500


@app.route('/api/analytics', methods=['GET'])
def api_analytics():
    """Get conversation analytics"""
    try:
        analytics = {
            'total_conversations': len(conversations),
            'active_sessions': len([c for c in conversations.values() if
                                    (datetime.now() - datetime.fromisoformat(
                                        c['last_update'])).total_seconds() < 3600]),
            'total_messages': sum(len(c['messages']) for c in conversations.values()),
            'avg_conversation_length': sum(c['message_count'] for c in conversations.values()) / len(
                conversations) if conversations else 0
        }

        # Token usage if available
        total_tokens = sum(c.get('total_tokens_used', 0) for c in conversations.values())
        if total_tokens > 0:
            analytics['openai_usage'] = {
                'total_tokens': total_tokens,
                'estimated_cost_usd': total_tokens * 0.002 / 1000  # Rough estimate
            }

        return jsonify({
            'analytics': analytics,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({'error': 'Could not generate analytics'}), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == "__main__":
    # Startup checks
    print("🌱 Starting GrowVRD - Concise Plant Expert")
    print("=" * 50)

    # Check OpenAI
    if os.getenv('OPENAI_API_KEY'):
        print("✅ OpenAI API key found")
        if enhanced_chat_available:
            print("✅ Enhanced concise chat system loaded")

        # Test connection
        try:
            if openai_client:
                test_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "Test"}],
                    max_tokens=5
                )
                print(f"✅ OpenAI connection verified ({test_response.usage.total_tokens} tokens)")
        except Exception as e:
            print(f"❌ OpenAI connection failed: {e}")
    else:
        print("❌ OpenAI API key not found")

    # Check DynamoDB
    if dynamo_connector:
        print("✅ DynamoDB connector available")
    else:
        print("⚠️ DynamoDB not available (using fallback)")

    print("\n🚀 Ready to provide concise, warm plant expertise!")
    print("📍 Chat endpoint: /api/chat")
    print("🔍 Health check: /api/health")

    # Run the app
    app.run(debug=True, host='0.0.0.0', port=5000)