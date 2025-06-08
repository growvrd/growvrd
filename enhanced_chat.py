#!/usr/bin/env python3
"""
Enhanced Chat System for GrowVRD - Optimized for OpenAI
Maximum ChatGPT-like experience with DynamoDB integration
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('enhanced_chat')

# Initialize OpenAI with optimal settings
openai_client = None
try:
    from openai import OpenAI

    openai_client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
        timeout=30.0,  # Increased timeout for better reliability
        max_retries=3  # Automatic retries for resilience
    )
    logger.info("✅ OpenAI client initialized with premium settings")
except Exception as e:
    logger.error(f"❌ OpenAI setup failed: {e}")

# Initialize AWS DynamoDB
dynamo_connector = None
try:
    from aws.dynamo_connector import DynamoConnector

    dynamo_connector = DynamoConnector(
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        table_prefix='growvrd'
    )


    # Override table names to match your migrated tables
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
    logger.info("✅ DynamoDB connector loaded with migrated data")

except Exception as e:
    logger.warning(f"DynamoDB connector not available: {e}")


class AdvancedPlantExpert:
    """Advanced OpenAI-powered plant expert with DynamoDB integration"""

    def __init__(self):
        self.conversation_cache = {}
        self.plant_data_cache = None
        self.product_data_cache = None
        self.cache_timestamp = None
        self.cache_duration = timedelta(minutes=10)  # Cache data for 10 minutes

        # Advanced conversation settings
        self.model = "gpt-3.5-turbo"
        self.max_tokens = 800  # Increased for more detailed responses
        self.temperature = 0.7
        self.presence_penalty = 0.1  # Encourages variety in responses
        self.frequency_penalty = 0.1  # Reduces repetition

        logger.info("🌿 Advanced Plant Expert initialized")

    def get_cached_plant_data(self) -> List[Dict[str, Any]]:
        """Get cached plant data from DynamoDB"""
        now = datetime.now()

        if (self.plant_data_cache is None or
                self.cache_timestamp is None or
                now - self.cache_timestamp > self.cache_duration):

            try:
                if dynamo_connector:
                    self.plant_data_cache = dynamo_connector.get_plants()
                    self.cache_timestamp = now
                    logger.info(f"Cached {len(self.plant_data_cache)} plants from DynamoDB")
                else:
                    self.plant_data_cache = []
            except Exception as e:
                logger.error(f"Error caching plant data: {e}")
                self.plant_data_cache = []

        return self.plant_data_cache or []

    def get_cached_product_data(self) -> List[Dict[str, Any]]:
        """Get cached product data from DynamoDB"""
        now = datetime.now()

        if (self.product_data_cache is None or
                self.cache_timestamp is None or
                now - self.cache_timestamp > self.cache_duration):

            try:
                if dynamo_connector:
                    self.product_data_cache = dynamo_connector.get_products()
                    logger.info(f"Cached {len(self.product_data_cache)} products from DynamoDB")
                else:
                    self.product_data_cache = []
            except Exception as e:
                logger.error(f"Error caching product data: {e}")
                self.product_data_cache = []

        return self.product_data_cache or []

    def create_advanced_system_prompt(self, user_context: Dict[str, Any] = None) -> str:
        """Create advanced system prompt with real data context"""

        # Get available plant data for context
        plants = self.get_cached_plant_data()
        plant_count = len(plants)

        # Extract user's plant information
        user_plants = user_context.get('plants', []) if user_context else []
        user_plant_names = []
        user_plant_health = []

        for plant in user_plants:
            nickname = plant.get('nickname', plant.get('name', 'Unknown'))
            health = plant.get('health_status', 'unknown')
            location = plant.get('location_in_home', '')
            days_since_watered = plant.get('days_since_watered', 0)

            user_plant_names.append(nickname)
            if health == 'needs_attention':
                user_plant_health.append(f"{nickname} needs attention")
            elif days_since_watered and days_since_watered > 7:
                user_plant_health.append(f"{nickname} might need watering ({days_since_watered} days)")

        # Build comprehensive system prompt
        system_prompt = f"""You are GrowVRD, an expert plant consultant with 20+ years of experience and access to a comprehensive database of {plant_count} plants. You're enthusiastic, knowledgeable, and genuinely excited about helping people create thriving indoor gardens.

🌿 YOUR ADVANCED CAPABILITIES:
- Real-time access to comprehensive plant database with detailed care instructions
- Product compatibility ratings (1-5 scale) with specific warnings and recommendations  
- Personal plant tracking with health monitoring and care schedules
- Room condition analysis and optimal placement strategies
- Advanced troubleshooting with step-by-step solutions
- Amazon product integration with affiliate links and pricing

💬 YOUR EXPERT PERSONALITY:
- Warm, encouraging, and genuinely passionate about plants
- Ask thoughtful follow-up questions to understand specific needs
- Provide detailed, actionable advice with scientific backing
- Use emojis naturally to convey enthusiasm and warmth
- Remember and reference previous conversations and user preferences
- Share interesting plant facts and care insights

🎯 YOUR CONSULTATION APPROACH:
1. **Active Listening** - Understand their space, experience level, lifestyle, and goals
2. **Specific Recommendations** - Never generic advice; always specific to their situation
3. **Educational Explanations** - Explain the 'why' behind your recommendations
4. **Proactive Care Planning** - Anticipate future needs and seasonal changes
5. **Ongoing Support** - Follow up on plant health and provide continuous guidance

📊 YOUR DATA INTELLIGENCE:
- Reference specific care requirements from your plant database
- Warn about product incompatibilities (ratings 1-2 = avoid, 4-5 = highly recommend)
- Provide realistic watering schedules based on actual plant needs and seasons
- Suggest complementary plants that thrive in similar conditions
- Recommend local vendors when beneficial for specialized needs"""

        # Add user-specific context
        if user_context:
            if user_plant_names:
                system_prompt += f"\n\n👤 USER'S CURRENT GARDEN:\n"
                system_prompt += f"Plants: {', '.join(user_plant_names)}\n"

                if user_plant_health:
                    system_prompt += f"Health alerts: {'; '.join(user_plant_health)}\n"

            if user_context.get('preferences'):
                prefs = user_context['preferences']
                if prefs.get('experience_level'):
                    system_prompt += f"Experience level: {prefs['experience_level']}\n"
                if prefs.get('care_style'):
                    system_prompt += f"Preferred care style: {prefs['care_style']}\n"

            if user_context.get('room_conditions'):
                rooms = list(user_context['room_conditions'].keys())
                if rooms:
                    system_prompt += f"Available spaces: {', '.join(rooms)}\n"

        system_prompt += """

🌱 CONVERSATION GUIDELINES:
- Always be encouraging and build confidence in their plant parenting abilities
- When suggesting plants, mention specific care requirements and why they're perfect for the user
- Include compatibility warnings for products (mention ratings and explain concerns)
- Ask follow-up questions to provide increasingly personalized advice
- Reference their existing plants when relevant to build continuity
- Provide seasonal care tips and adjustments when appropriate

Remember: You're not just answering questions - you're helping someone build a lasting, joyful relationship with plants! Every interaction should leave them feeling more confident and excited about their plant journey. 🌟"""

        return system_prompt

    def analyze_message_intent(self, message: str, user_context: Dict = None) -> Dict[str, Any]:
        """Analyze user message to understand intent and provide context"""
        message_lower = message.lower()

        intent_analysis = {
            'type': 'general',
            'confidence': 0.5,
            'keywords': [],
            'mentioned_plants': [],
            'user_plants_mentioned': [],
            'urgency': 'normal'
        }

        # Detect message type
        if any(word in message_lower for word in ['recommend', 'suggest', 'need', 'want', 'looking for', 'best plant']):
            intent_analysis['type'] = 'recommendation'
            intent_analysis['confidence'] = 0.9
        elif any(
                word in message_lower for word in ['dying', 'yellow', 'brown', 'problem', 'sick', 'help', 'emergency']):
            intent_analysis['type'] = 'emergency'
            intent_analysis['urgency'] = 'high'
            intent_analysis['confidence'] = 0.95
        elif any(word in message_lower for word in ['water', 'care', 'how to', 'when', 'fertilize']):
            intent_analysis['type'] = 'care_guidance'
            intent_analysis['confidence'] = 0.85
        elif any(word in message_lower for word in ['buy', 'product', 'pot', 'soil', 'fertilizer', 'light']):
            intent_analysis['type'] = 'product_advice'
            intent_analysis['confidence'] = 0.8

        # Detect mentioned plants
        common_plants = [
            'snake plant', 'pothos', 'monstera', 'fiddle leaf fig', 'rubber tree',
            'spider plant', 'peace lily', 'zz plant', 'philodendron', 'succulent',
            'cactus', 'aloe', 'jade plant', 'fern', 'ivy'
        ]

        for plant in common_plants:
            if plant in message_lower:
                intent_analysis['mentioned_plants'].append(plant)

        # Check for user's specific plants
        if user_context and user_context.get('plants'):
            for plant in user_context['plants']:
                nickname = plant.get('nickname', '').lower()
                name = plant.get('name', '').lower()
                if nickname and nickname in message_lower:
                    intent_analysis['user_plants_mentioned'].append(nickname)
                elif name and name in message_lower:
                    intent_analysis['user_plants_mentioned'].append(name)

        return intent_analysis

    def get_relevant_data_context(self, message: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Get relevant plant and product data based on message intent"""
        context = {
            'relevant_plants': [],
            'relevant_products': [],
            'compatibility_warnings': []
        }

        try:
            if intent['type'] == 'recommendation':
                # Get plant recommendations
                plants = self.get_smart_plant_recommendations(message)
                context['relevant_plants'] = plants[:5]  # Top 5 recommendations

                # Get products for top plant
                if plants:
                    top_plant_id = plants[0].get('id')
                    if top_plant_id:
                        products = self.get_compatible_products_with_ratings(top_plant_id)
                        context['relevant_products'] = products[:3]

            elif intent['type'] in ['care_guidance', 'emergency']:
                # Get specific plant data if mentioned
                if intent['mentioned_plants']:
                    plant_name = intent['mentioned_plants'][0]
                    plants = self.get_cached_plant_data()
                    relevant_plant = next((p for p in plants if plant_name.lower() in p.get('name', '').lower()), None)
                    if relevant_plant:
                        context['relevant_plants'] = [relevant_plant]

            elif intent['type'] == 'product_advice':
                # Get general product recommendations
                products = self.get_cached_product_data()
                context['relevant_products'] = products[:5]

        except Exception as e:
            logger.error(f"Error getting relevant data: {e}")

        return context

    def get_smart_plant_recommendations(self, query: str) -> List[Dict[str, Any]]:
        """Get intelligent plant recommendations with advanced scoring"""
        try:
            plants = self.get_cached_plant_data()
            recommendations = []
            query_lower = query.lower()

            for plant in plants:
                score = 0
                scoring_reasons = []

                plant_name = plant.get('name', '').lower()
                plant_desc = plant.get('description', '').lower()

                # Name matching (high weight)
                if any(word in plant_name for word in query_lower.split()):
                    score += 40
                    scoring_reasons.append("name match")

                # Description matching
                if any(word in plant_desc for word in query_lower.split()):
                    score += 25
                    scoring_reasons.append("description match")

                # Light condition matching
                light_needs = plant.get('natural_sunlight_needs', '').lower()
                if 'low light' in query_lower or 'dark' in query_lower:
                    if light_needs == 'low':
                        score += 35
                        scoring_reasons.append("perfect for low light")
                elif 'bright' in query_lower or 'sunny' in query_lower:
                    if light_needs in ['high', 'bright']:
                        score += 35
                        scoring_reasons.append("loves bright light")
                elif 'medium' in query_lower or 'indirect' in query_lower:
                    if light_needs == 'medium':
                        score += 35
                        scoring_reasons.append("ideal for medium light")

                # Experience level matching
                difficulty = plant.get('difficulty', 5)
                if isinstance(difficulty, (int, float)):
                    if 'easy' in query_lower or 'beginner' in query_lower:
                        if difficulty <= 3:
                            score += 30
                            scoring_reasons.append("beginner-friendly")
                    elif 'advanced' in query_lower or 'challenging' in query_lower:
                        if difficulty >= 7:
                            score += 30
                            scoring_reasons.append("rewarding challenge")

                # Location/room matching
                compatible_locations = plant.get('compatible_locations', [])
                if isinstance(compatible_locations, list):
                    location_str = ' '.join(compatible_locations).lower()
                    for room in ['bedroom', 'bathroom', 'kitchen', 'living room', 'office']:
                        if room in query_lower and room in location_str:
                            score += 25
                            scoring_reasons.append(f"perfect for {room}")

                # Maintenance level matching
                maintenance = plant.get('maintenance', '').lower()
                if 'low maintenance' in query_lower and maintenance == 'low':
                    score += 25
                    scoring_reasons.append("very low maintenance")
                elif 'high maintenance' in query_lower and maintenance == 'high':
                    score += 25
                    scoring_reasons.append("rewards attentive care")

                # Size preferences
                size = plant.get('size', '').lower()
                if 'small' in query_lower and 'small' in size:
                    score += 20
                    scoring_reasons.append("perfect size")
                elif 'large' in query_lower and 'large' in size:
                    score += 20
                    scoring_reasons.append("impressive size")

                if score > 0:
                    plant_copy = plant.copy()
                    plant_copy['match_score'] = score
                    plant_copy['normalized_score'] = min(score, 100)
                    plant_copy['scoring_reasons'] = scoring_reasons
                    recommendations.append(plant_copy)

            # Sort by score and return top results
            recommendations.sort(key=lambda x: x.get('match_score', 0), reverse=True)
            return recommendations[:8]

        except Exception as e:
            logger.error(f"Error getting smart recommendations: {e}")
            return []

    def get_compatible_products_with_ratings(self, plant_id: str) -> List[Dict[str, Any]]:
        """Get compatible products with detailed ratings and warnings"""
        try:
            if not dynamo_connector:
                return []

            # Get plant-product relationships
            relationships = dynamo_connector.get_products_for_plant(plant_id)
            compatible_products = []

            for relationship in relationships:
                product_id = relationship.get('product_id')
                compatibility_rating = relationship.get('compatibility_rating', 3)
                compatibility_notes = relationship.get('compatibility_notes', '')

                if product_id:
                    # Get the actual product data
                    products = self.get_cached_product_data()
                    product = next((p for p in products if p.get('id') == product_id), None)

                    if product:
                        product_copy = product.copy()
                        product_copy['compatibility_rating'] = compatibility_rating
                        product_copy['compatibility_notes'] = compatibility_notes
                        product_copy['primary_purpose'] = relationship.get('primary_purpose', '')

                        # Add recommendation level
                        if compatibility_rating >= 5:
                            product_copy['recommendation_level'] = 'essential'
                            product_copy['recommendation_text'] = f"✅ Perfect match: {compatibility_notes}"
                        elif compatibility_rating >= 4:
                            product_copy['recommendation_level'] = 'highly_recommended'
                            product_copy['recommendation_text'] = f"👍 Excellent choice: {compatibility_notes}"
                        elif compatibility_rating >= 3:
                            product_copy['recommendation_level'] = 'compatible'
                            product_copy['recommendation_text'] = f"✔️ Good option: {compatibility_notes}"
                        else:
                            product_copy['recommendation_level'] = 'warning'
                            product_copy['recommendation_text'] = f"⚠️ Caution: {compatibility_notes}"

                        compatible_products.append(product_copy)

            # Sort by compatibility rating
            compatible_products.sort(key=lambda x: x.get('compatibility_rating', 0), reverse=True)
            return compatible_products[:6]

        except Exception as e:
            logger.error(f"Error getting compatible products: {e}")
            return []

    def generate_enhanced_response(
            self,
            message: str,
            conversation_history: List[Dict] = None,
            user_context: Dict = None
    ) -> Dict[str, Any]:
        """Generate enhanced OpenAI response with data integration"""

        if not openai_client:
            return self._fallback_response(message)

        try:
            # Analyze the message
            intent = self.analyze_message_intent(message, user_context)
            data_context = self.get_relevant_data_context(message, intent)

            # Build optimized conversation
            messages = self._build_optimized_conversation(
                message, conversation_history, user_context, intent, data_context
            )

            # Generate OpenAI response with optimal settings
            response = openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                presence_penalty=self.presence_penalty,
                frequency_penalty=self.frequency_penalty,
                timeout=30
            )

            ai_content = response.choices[0].message.content

            # Get enhanced data based on intent
            plants_data = data_context.get('relevant_plants', [])
            products_data = data_context.get('relevant_products', [])

            # If this was a recommendation request, ensure we have recommendations
            if intent['type'] == 'recommendation' and not plants_data:
                plants_data = self.get_smart_plant_recommendations(message)[:3]
                if plants_data:
                    top_plant_id = plants_data[0].get('id')
                    if top_plant_id:
                        products_data = self.get_compatible_products_with_ratings(top_plant_id)[:2]

            return {
                'type': 'text',
                'content': ai_content,
                'plants': plants_data,
                'products': products_data,
                'intent': intent,
                'enhanced': True,
                'provider': 'openai_optimized',
                'model_used': self.model,
                'tokens_used': response.usage.total_tokens if hasattr(response, 'usage') else None,
                'timestamp': datetime.now().isoformat(),
                'success': True
            }

        except Exception as e:
            logger.error(f"Enhanced OpenAI response error: {e}")
            return self._fallback_response(message, error=str(e))

    def _build_optimized_conversation(
            self,
            message: str,
            history: List[Dict],
            user_context: Dict,
            intent: Dict,
            data_context: Dict
    ) -> List[Dict[str, str]]:
        """Build optimized conversation for OpenAI"""

        messages = []

        # System prompt with full context
        system_prompt = self.create_advanced_system_prompt(user_context)
        messages.append({"role": "system", "content": system_prompt})

        # Add relevant data context if available
        if data_context.get('relevant_plants') or data_context.get('relevant_products'):
            context_info = "RELEVANT DATA CONTEXT:\n"

            if data_context.get('relevant_plants'):
                context_info += f"Available plants: {len(data_context['relevant_plants'])} matching options\n"
                for plant in data_context['relevant_plants'][:3]:
                    context_info += f"- {plant.get('name')}: {plant.get('description', '')[:100]}...\n"

            if data_context.get('relevant_products'):
                context_info += f"Compatible products: {len(data_context['relevant_products'])} options\n"
                for product in data_context['relevant_products'][:2]:
                    rating = product.get('compatibility_rating', 'N/A')
                    context_info += f"- {product.get('name')} (Rating: {rating}/5)\n"

            messages.append({"role": "system", "content": context_info})

        # Add conversation history (optimized for token usage)
        if history:
            # For emergency/problem messages, include more history for context
            history_limit = 10 if intent['urgency'] == 'high' else 6

            for msg in history[-history_limit:]:
                role = msg.get('role', 'user')
                content = msg.get('content', '')

                # Trim very long messages to save tokens
                if len(content) > 500:
                    content = content[:500] + "..."

                messages.append({"role": role, "content": content})

        # Add current message with intent context
        enhanced_message = message
        if intent['urgency'] == 'high':
            enhanced_message = f"[URGENT PLANT ISSUE] {message}"
        elif intent['type'] == 'recommendation':
            enhanced_message = f"[PLANT RECOMMENDATION REQUEST] {message}"

        messages.append({"role": "user", "content": enhanced_message})

        return messages

    def _fallback_response(self, message: str, error: str = None) -> Dict[str, Any]:
        """Fallback response when OpenAI is unavailable"""
        return {
            'type': 'error',
            'content': "I'm having trouble connecting to my advanced AI system right now. Let me help you with my basic plant knowledge! What specific plant question can I answer?",
            'enhanced': False,
            'provider': 'fallback',
            'error': error,
            'timestamp': datetime.now().isoformat(),
            'success': False
        }


# Global instance
_advanced_expert = None


def get_advanced_expert() -> AdvancedPlantExpert:
    """Get global advanced expert instance"""
    global _advanced_expert
    if _advanced_expert is None:
        _advanced_expert = AdvancedPlantExpert()
    return _advanced_expert


def enhanced_chat_response(
        message: str,
        conversation_history: List[Dict] = None,
        user_context: Dict = None
) -> Dict[str, Any]:
    """Main enhanced chat function optimized for OpenAI"""
    try:
        expert = get_advanced_expert()
        return expert.generate_enhanced_response(message, conversation_history, user_context)
    except Exception as e:
        logger.error(f"Enhanced chat error: {e}")
        return {
            'type': 'error',
            'content': "I'm experiencing a technical difficulty. Let me know what plant question you have and I'll do my best to help! 🌱",
            'enhanced': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat(),
            'success': False
        }


def get_plant_recommendations_with_data(query: str, user_context: Dict = None) -> List[Dict[str, Any]]:
    """Get plant recommendations with advanced scoring"""
    try:
        expert = get_advanced_expert()
        return expert.get_smart_plant_recommendations(query)
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return []


def get_compatible_products(plant_id: str) -> List[Dict[str, Any]]:
    """Get compatible products with detailed ratings"""
    try:
        expert = get_advanced_expert()
        return expert.get_compatible_products_with_ratings(plant_id)
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return []


# Export main functions
__all__ = [
    'enhanced_chat_response',
    'get_plant_recommendations_with_data',
    'get_compatible_products',
    'dynamo_connector'
]


# Test function for debugging
def test_advanced_chat():
    """Test the advanced chat system"""
    if not openai_client:
        print("❌ OpenAI client not available")
        return

    print("🧪 Testing Advanced OpenAI Integration...")
    expert = get_advanced_expert()

    test_messages = [
        "I need a plant for my dark bedroom that's easy to care for",
        "My snake plant has yellow leaves, what's wrong?",
        "What's the best pot for a fiddle leaf fig?"
    ]

    for message in test_messages:
        print(f"\n👤 User: {message}")
        response = expert.generate_enhanced_response(message)
        print(f"🤖 GrowVRD: {response['content'][:200]}...")
        print(f"   Model: {response.get('model_used', 'unknown')}")
        print(f"   Tokens: {response.get('tokens_used', 'unknown')}")
        print(f"   Plants: {len(response.get('plants', []))}")
        print(f"   Products: {len(response.get('products', []))}")


if __name__ == "__main__":
    test_advanced_chat()