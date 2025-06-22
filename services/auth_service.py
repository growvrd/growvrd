class AuthService:
    def authenticate(self, credentials):
        if not credentials:
            return {'error': 'No credentials provided'}
        
        return {
            'token': f"token_{str(hash(str(credentials)))}",
            'user_id': 1,
            'name': 'Demo User'
        }
    
    def validate_token(self, token):
        return token.startswith('token_')
