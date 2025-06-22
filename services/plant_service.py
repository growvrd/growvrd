class PlantService:
    def get_all(self):
        return [
            {'id': 1, 'name': 'Snake Plant', 'care_level': 'easy'},
            {'id': 2, 'name': 'Monstera', 'care_level': 'medium'}
        ]
    
    def get_recommendations(self, user_data):
        return {'plants': self.get_all()[:2]}
