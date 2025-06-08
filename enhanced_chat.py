#!/usr/bin/env python3
"""
Enhanced Chat System - Optimized for Concise, Warm Expert Plant Advice
GrowVRD AI Plant Assistant with OpenAI Integration
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = None
try:
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    logger.info("✅ OpenAI client initialized")
except Exception as e:
    logger.error(f"❌ OpenAI initialization failed: {e}")

# DynamoDB integration
dynamo_connector = None
try:
    from aws.dynamo_connector import DynamoDBConnector

    table_name_map = {
        'plants': 'growvrd-plants-development',
        'products': 'growvrd-products-development',
        'users': 'growvrd-users-development',
        'plant_products': 'growvrd-plant-products-development',
        'user_plants': 'growvrd-user-plants-development',
        'vendors': 'growvrd-local-vendors-development',
        'kits': 'growvrd-kits-development'
    }

    dynamo_connector = DynamoDBConnector()
    dynamo_connector._get_table_name = lambda table_type: table_name_map.get(
        table_type, f"growvrd-{table_type}-development"
    )

    logger.info("✅ DynamoDB connector loaded")
except Exception as e:
    logger.warning(f"⚠️ DynamoDB not available: {e}")


class ConcisePlantExpert:
    """Optimized plant expert for warm, concise responses"""

    def __init__(self):
        self.cache = {
            'plants': None,
            'products': None,
            'timestamp': None
        }
        self.cache_duration = timedelta(minutes=15)

        # Optimized OpenAI settings for concise responses
        self.model = "gpt-3.5-turbo"
        self.max_tokens = 120  # Perfect for 2-3 sentences
        self.temperature = 0.8  # Slightly higher for warmth
        self.presence_penalty = 0.2  # Encourage variety
        self.frequency_penalty = 0.3  # Reduce repetition

        logger.info("🌱 Concise Plant Expert initialized")

    def _refresh_cache(self):
        """Refresh data cache if needed"""
        now = datetime.now()
        if (not self.cache['timestamp'] or
                now - self.cache['timestamp'] > self.cache_duration):

            try:
                if dynamo_connector:
                    self.cache['plants'] = dynamo_connector.get_plants()
                    self.cache['products'] = dynamo_connector.get_products()
                    self.cache['timestamp'] = now
                    logger.info(f"📊 Cached {len(self.cache['plants'])} plants, {len(self.cache['products'])} products")
                else:
                    self.cache['plants'] = []
                    self.cache['products'] = []
            except Exception as e:
                logger.error(f"Cache refresh error: {e}")
                self.cache['plants'] = []
                self.cache['products'] = []

    def create_expert_prompt(self, user_context: Dict = None) -> str:
        """Create optimized system prompt for concise, warm responses"""

        base_prompt = """You are GrowVRD, a beloved plant expert with 20+ years of experience. You're like that friend who always knows exactly what plants to recommend and gives perfect advice.

🎯 RESPONSE STYLE:
- Keep responses to 2-3 sentences maximum
- Be warm, encouraging, and genuinely excited about plants
- Give specific, actionable advice
- Ask ONE follow-up question when helpful
- Use 1-2 emojis naturally for warmth

💚 YOUR EXPERTISE:
- Access to comprehensive plant database with care details
- Product compatibility ratings (1-5 scale, warn about 1-2 ratings)
- Personal plant tracking and health monitoring
- Room-specific placement recommendations

🌿 CONVERSATION APPROACH:
- Listen first, then recommend specifically
- Reference user's existing plants when relevant
- Explain WHY briefly for confidence building
- Suggest complete solutions (plant + perfect products)
- Always end with encouragement or curiosity

Remember: You're not just answering questions - you're building plant confidence and joy! 🌱"""

        # Add user context if available
        if user_context:
            user_plants = user_context.get('plants', [])
            if user_plants:
                plant_names = [p.get('nickname', p.get('name', 'Unknown')) for p in user_plants]
                base_prompt += f"\n\n👤 USER'S PLANTS: {', '.join(plant_names[:3])}"

                # Check for plants needing attention
                attention_plants = [p.get('nickname', p.get('name')) for p in user_plants
                                    if p.get('health_status') == 'needs_attention']
                if attention_plants:
                    base_prompt += f"\n⚠️ PLANTS NEEDING ATTENTION: {', '.join(attention_plants)}"

        return base_prompt

    def analyze_intent(self, message: str) -> Dict[str, Any]:
        """Quick intent analysis for response optimization"""
        message_lower = message.lower()

        intent = {
            'type': 'general',
            'urgency': 'normal',
            'confidence': 0.5
        }

        # Emergency detection
        if any(word in message_lower for word in ['dying', 'yellow', 'brown', 'help', 'emergency', 'sick']):
            intent.update({'type': 'emergency', 'urgency': 'high', 'confidence': 0.95})

        # Recommendation requests
        elif any(word in message_lower for word in ['recommend', 'suggest', 'need', 'want', 'looking for']):
            intent.update({'type': 'recommendation', 'confidence': 0.9})

        # Care guidance
        elif any(word in message_lower for word in ['water', 'care', 'how', 'when', 'fertilize']):
            intent.update({'type': 'care', 'confidence': 0.85})

        # Product advice
        elif any(word in message_lower for word in ['pot', 'soil', 'light', 'buy', 'product']):
            intent.update({'type': 'product', 'confidence': 0.8})

        return intent

    def get_relevant_data(self, message: str, intent: Dict) -> Dict[str, Any]:
        """Get relevant plants/products based on message"""
        self._refresh_cache()

        context = {'plants': [], 'products': []}

        try:
            if intent['type'] == 'recommendation':
                # Quick plant matching
                plants = self.cache['plants'] or []
                message_lower = message.lower()

                scored_plants = []
                for plant in plants:
                    score = 0
                    name = plant.get('name', '').lower()
                    desc = plant.get('description', '').lower()

                    # Quick scoring
                    if any(word in name for word in ['easy', 'beginner'] if 'easy' in message_lower):
                        score += 3
                    if any(word in desc for word in ['low light'] if 'dark' in message_lower):
                        score += 3
                    if any(word in desc for word in ['drought'] if 'busy' in message_lower):
                        score += 2

                    if score > 0:
                        plant['match_score'] = score
                        scored_plants.append(plant)

                context['plants'] = sorted(scored_plants, key=lambda x: x.get('match_score', 0), reverse=True)[:3]

                # Get products for top plant
                if context['plants']:
                    top_plant_id = context['plants'][0].get('id')
                    context['products'] = self.get_compatible_products(top_plant_id)[:2]

        except Exception as e:
            logger.error(f"Data context error: {e}")

        return context

    def get_compatible_products(self, plant_id: str) -> List[Dict]:
        """Get compatible products with ratings"""
        try:
            products = self.cache['products'] or []
            compatible = []

            for product in products:
                # Simple compatibility check (expand based on your data structure)
                rating = product.get('compatibility_rating', 3)
                if rating >= 3:  # Only show good matches
                    product_copy = product.copy()
                    product_copy['rating'] = rating
                    compatible.append(product_copy)

            return sorted(compatible, key=lambda x: x.get('rating', 0), reverse=True)

        except Exception as e:
            logger.error(f"Product compatibility error: {e}")
            return []

    def generate_response(self, message: str, history: List[Dict] = None, user_context: Dict = None) -> Dict[str, Any]:
        """Generate concise, warm expert response"""

        if not openai_client:
            return self._fallback_response(message)

        try:
            # Analyze and prepare
            intent = self.analyze_intent(message)
            data_context = self.get_relevant_data(message, intent)

            # Build conversation
            messages = [
                {"role": "system", "content": self.create_expert_prompt(user_context)}
            ]

            # Add relevant data context
            if data_context['plants'] or data_context['products']:
                context_info = "AVAILABLE OPTIONS:\n"

                for plant in data_context['plants'][:2]:
                    context_info += f"🌱 {plant.get('name')}: {plant.get('description', '')[:60]}...\n"

                for product in data_context['products'][:1]:
                    rating = product.get('rating', 'N/A')
                    context_info += f"🛍️ {product.get('name')} (Rating: {rating}/5)\n"

                messages.append({"role": "system", "content": context_info})

            # Add recent history (keep it short)
            if history:
                for msg in history[-3:]:  # Only last 3 messages
                    if len(msg.get('content', '')) < 200:  # Skip very long messages
                        messages.append({
                            "role": msg.get('role', 'user'),
                            "content": msg['content']
                        })

            # Add current message with urgency context
            current_message = message
            if intent['urgency'] == 'high':
                current_message = f"[URGENT PLANT ISSUE] {message}"

            messages.append({"role": "user", "content": current_message})

            # Generate OpenAI response
            response = openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                presence_penalty=self.presence_penalty,
                frequency_penalty=self.frequency_penalty,
                timeout=20
            )

            content = response.choices[0].message.content

            return {
                'type': 'text',
                'content': content,
                'plants': data_context.get('plants', []),
                'products': data_context.get('products', []),
                'intent': intent,
                'enhanced': True,
                'provider': 'openai_concise',
                'model_used': self.model,
                'tokens_used': response.usage.total_tokens if hasattr(response, 'usage') else None,
                'timestamp': datetime.now().isoformat(),
                'success': True
            }

        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._fallback_response(message, str(e))

    def _fallback_response(self, message: str, error: str = None) -> Dict[str, Any]:
        """Warm fallback when OpenAI unavailable"""

        fallback_responses = [
            "I'm having a tiny tech hiccup! 🌱 What specific plant question can I help you with?",
            "Oops, my plant brain needs a quick refresh! What are you curious about? 🌿",
            "Technical wobble on my end! Tell me about your plant situation and I'll help! 💚"
        ]

        import random
        content = random.choice(fallback_responses)

        return {
            'type': 'text',
            'content': content,
            'plants': [],
            'products': [],
            'enhanced': False,
            'provider': 'fallback',
            'error': error,
            'timestamp': datetime.now().isoformat(),
            'success': False
        }


# Global expert instance
_expert = None


def get_expert() -> ConcisePlantExpert:
    """Get global expert instance"""
    global _expert
    if _expert is None:
        _expert = ConcisePlantExpert()
    return _expert


def enhanced_chat_response(message: str, conversation_history: List[Dict] = None, user_context: Dict = None) -> Dict[
    str, Any]:
    """Main chat function - optimized for concise responses"""
    try:
        expert = get_expert()
        return expert.generate_response(message, conversation_history, user_context)
    except Exception as e:
        logger.error(f"Enhanced chat error: {e}")
        return {
            'type': 'error',
            'content': "Quick plant question hiccup! What would you like to know? 🌱",
            'enhanced': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat(),
            'success': False
        }


def get_plant_recommendations_with_data(query: str, user_context: Dict = None) -> List[Dict[str, Any]]:
    """Get plant recommendations with scoring"""
    try:
        expert = get_expert()
        expert._refresh_cache()

        intent = expert.analyze_intent(query)
        data_context = expert.get_relevant_data(query, intent)
        return data_context.get('plants', [])
    except Exception as e:
        logger.error(f"Recommendations error: {e}")
        return []


def get_compatible_products(plant_id: str) -> List[Dict[str, Any]]:
    """Get compatible products for plant"""
    try:
        expert = get_expert()
        return expert.get_compatible_products(plant_id)
    except Exception as e:
        logger.error(f"Products error: {e}")
        return []


# Export main functions
__all__ = [
    'enhanced_chat_response',
    'get_plant_recommendations_with_data',
    'get_compatible_products',
    'dynamo_connector'
]


# Quick test function
def test_concise_chat():
    """Test the concise chat system"""
    if not openai_client:
        print("❌ OpenAI not available")
        return

    print("🧪 Testing Concise Plant Expert...")
    expert = get_expert()

    test_messages = [
        "I need an easy plant for my dark bedroom",
        "My snake plant has yellow leaves help!",
        "What pot should I get for pothos?"
    ]

    for msg in test_messages:
        print(f"\n👤 {msg}")
        response = expert.generate_response(msg)
        print(f"🤖 {response['content']}")
        print(f"   Tokens: {response.get('tokens_used', 0)}")


if __name__ == "__main__":
    test_concise_chat()