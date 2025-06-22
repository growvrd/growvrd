from flask import Flask, Response, jsonify, request, send_from_directory, session
from typing import Dict, Any, Tuple, Optional
import os
import logging
from services import (
    ChatService,
    PlantService,
    PaymentService,
    AuthService,
    SubscriptionService,
    SubscriptionTier
)

# Set up logging
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__, static_folder='static')
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    
    services = {
        'chat': ChatService(),
        'plants': PlantService(),
        'payments': PaymentService(),
        'auth': AuthService(),
        'subscription': SubscriptionService()
    }

    @app.route('/')
    def index():
        return send_from_directory('static', 'index.html')

    @app.route('/chat')
    def chat():
        return send_from_directory('static', 'chat.html')

    @app.route('/api/chat', methods=['POST'])
    def api_chat():
        data = request.get_json()
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message required'}), 400
        return jsonify(services['chat'].process(message, session))

    @app.route('/api/plants', methods=['GET'])
    def get_plants():
        return jsonify(services['plants'].get_all())

    @app.route('/api/checkout', methods=['POST'])
    def create_checkout():
        return jsonify(services['payments'].create_checkout(request.json))

    @app.route('/api/login', methods=['POST'])
    def login() -> Response:
        """Handle user login and return auth result with subscription info."""
        try:
            if not request.json or 'email' not in request.json or 'password' not in request.json:
                return jsonify({'error': 'Email and password are required'}), 400
                
            auth_result = services['auth'].authenticate(request.json)
            if not isinstance(auth_result, dict):
                return jsonify({'error': 'Invalid authentication response'}), 500
                
            if auth_result.get('success', False):
                # Add subscription info to auth response
                email = request.json.get('email')
                if email:
                    subscription = services['subscription'].get_subscription_details(email)
                    auth_result['subscription'] = subscription
            return jsonify(auth_result)
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
        
    @app.route('/api/subscription', methods=['GET'])
    def get_subscription() -> Response:
        """Get subscription details for a user."""
        try:
            email = request.args.get('email')
            if not email or not isinstance(email, str):
                return jsonify({'error': 'Valid email is required'}), 400
                
            subscription = services['subscription'].get_subscription_details(email)
            if not isinstance(subscription, dict):
                return jsonify({'error': 'Failed to get subscription details'}), 500
                
            return jsonify(subscription)
            
        except Exception as e:
            logger.error(f"Subscription error: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
        
    @app.route('/api/check-feature', methods=['GET'])
    def check_feature() -> Response:
        """Check if a user has access to a specific feature and their quota."""
        try:
            email = request.args.get('email')
            feature = request.args.get('feature')
            
            if not all([email, feature]) or not isinstance(email, str) or not isinstance(feature, str):
                return jsonify({'error': 'Valid email and feature are required'}), 400
                
            has_access = services['subscription'].can_access_feature(email, feature)
            has_quota, message, remaining = services['subscription'].check_quota(email, feature)
            
            return jsonify({
                'has_access': has_access,
                'has_quota': has_quota,
                'message': message,
                'remaining': remaining
            })
            
        except Exception as e:
            logger.error(f"Feature check error: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)