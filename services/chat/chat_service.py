"""Optimized chat service for plant advice with OpenAI integration."""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.cache = {'plants': [], 'products': [], 'timestamp': None}
        self.cache_duration = timedelta(minutes=15)
        self.model = "gpt-3.5-turbo"
        self.max_tokens = 120
        self.temperature = 0.8

    def _get_system_prompt(self, user_plants: List[Dict] = None) -> str:
        """Generate system prompt with user context."""
        prompt = """You're GrowVRD, a friendly plant expert. Keep responses to 2-3 sentences, be warm and specific. 
        Use emojis naturally. If suggesting plants, recommend 1-2 specific ones with brief care tips."""
        
        if user_plants:
            plant_names = [p.get('nickname', p.get('name')) for p in user_plants[:3]]
            prompt += f"\n\nUser's plants: {', '.join(plant_names)}"
            
            needs_attention = [p.get('nickname') for p in user_plants 
                            if p.get('health_status') == 'needs_attention']
            if needs_attention:
                prompt += f"\nNeeds attention: {', '.join(needs_attention)}"
                
        return prompt

    def _get_relevant_plants(self, query: str, plants: List[Dict]) -> List[Dict]:
        """Find plants relevant to the query."""
        if not plants or not query:
            return []
            
        query = query.lower()
        scored = []
        
        for plant in plants:
            score = 0
            name = plant.get('name', '').lower()
            desc = plant.get('description', '').lower()
            
            if 'easy' in query and 'easy' in desc:
                score += 2
            if 'low light' in query and 'low light' in desc:
                score += 2
            if any(word in query for word in ['dark', 'shady']) and 'low light' in desc:
                score += 2
                
            if score > 0:
                plant['match_score'] = score
                scored.append(plant)
                
        return sorted(scored, key=lambda x: x.get('match_score', 0), reverse=True)[:3]

    async def process_message(self, message: str, user_context: Dict = None) -> Dict[str, Any]:
        """Process user message and generate response."""
        try:
            # Get user's plants if available
            user_plants = user_context.get('plants', []) if user_context else []
            
            # Get relevant plants from database
            plants = self._get_relevant_plants(message, user_plants or [])
            
            # Build conversation
            messages = [
                {"role": "system", "content": self._get_system_prompt(user_plants)},
                {"role": "user", "content": message}
            ]
            
            # Add plant context if available
            if plants:
                context = "Available plants:\n"
                context += "\n".join(f"- {p.get('name')}: {p.get('description', '')[:100]}" 
                                     for p in plants)
                messages.insert(1, {"role": "system", "content": context})
            
            # Generate response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return {
                'success': True,
                'response': response.choices[0].message.content,
                'plants': plants[:2],
                'products': [],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {
                'success': False,
                'response': "I'm having trouble with that. Could you rephrase? 🌱",
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
