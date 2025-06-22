import logging
import os
import openai
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables")
        
        # Initialize conversation history
        self.conversation_history = [
            {"role": "system", "content": "You are a helpful plant expert that recommends indoor and outdoor plants based on user preferences. Ask questions one at a time to understand their needs regarding location, lighting, maintenance level, and purpose. Keep responses concise and friendly."}
        ]
    
    def _get_plant_recommendation(self, user_preferences: Dict[str, str]) -> str:
        try:
            if not self.openai_api_key:
                return "I'm sorry, the plant recommendation service is currently unavailable."
                
            openai.api_key = self.openai_api_key
            
            prompt = f"""Based on the following user preferences, recommend 3 suitable plants and provide a brief explanation for each:
            
            Location: {location}
            Lighting: {lighting}
            Maintenance Level: {maintenance}
            Purpose: {purpose}
            
            For each recommended plant, include:
            1. Plant name (common and scientific)
            2. Brief description
            3. Care requirements
            4. Why it's a good fit
            
            Format the response in a clean, easy-to-read way.""".format(
                location=user_preferences.get('location', 'Not specified'),
                lighting=user_preferences.get('lighting', 'Not specified'),
                maintenance=user_preferences.get('maintenance', 'Not specified'),
                purpose=user_preferences.get('purpose', 'Not specified')
            )
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful plant expert that provides detailed plant recommendations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            return response.choices[0].message['content'].strip()
            
        except Exception as e:
            logger.error(f"Error getting plant recommendation: {e}")
            return "I'm sorry, I encountered an error while processing your request. Please try again later."
    
    def process(self, message: str, session: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Store or update conversation history in session
            if 'conversation' not in session:
                session['conversation'] = []
                session['user_preferences'] = {}
            
            # Add user message to conversation history
            session['conversation'].append({"role": "user", "content": message})
            
            # Get response from OpenAI
            if self.openai_api_key:
                openai.api_key = self.openai_api_key
                
                # Prepare messages for OpenAI (system message + conversation history)
                messages = [
                    {"role": "system", "content": "You are a helpful plant expert that helps users find the perfect plants for their needs. Ask relevant questions about their location, lighting, maintenance preferences, and purpose to provide the best recommendations."}
                ] + session['conversation'][-6:]  # Keep last 3 exchanges (6 messages)
                
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=150,
                    temperature=0.7
                )
                
                bot_response = response.choices[0].message['content'].strip()
                
                # Add bot response to conversation history
                session['conversation'].append({"role": "assistant", "content": bot_response})
                
                return {
                    'response': bot_response,
                    'status': 'success'
                }
            else:
                return {
                    'response': "I'm sorry, the chat service is currently unavailable.",
                    'status': 'error'
                }
                
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")
            return {
                'response': 'Sorry, I encountered an error processing your message. Please try again.',
                'status': 'error'
            }
