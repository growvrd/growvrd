# GrowVRD - AI-Powered Plant Recommendation System

GrowVRD is an intelligent plant care and recommendation assistant that helps users select, maintain, and succeed with indoor plants based on their specific environment, experience level, and preferences.

## 🌱 Overview

GrowVRD uses a combination of expert plant knowledge and AI-powered recommendation algorithms to suggest plants that will thrive in your specific conditions. The system provides personalized recommendations based on:

- Room location (living room, bedroom, bathroom, etc.)
- Light conditions
- Experience level
- Maintenance preferences
- Environmental factors (temperature, humidity)

## ✨ Features

- **Personalized Plant Recommendations**: Get tailored plant suggestions based on your specific environment and preferences
- **Interactive Chat Interface**: Have natural conversations to discover the perfect plants for your space
- **Detailed Plant Information**: Access comprehensive care instructions and requirements for each plant
- **Product Recommendations**: Find the right pots, soil, and accessories for your plants
- **Pre-configured Plant Kits**: Explore curated collections for specific rooms or purposes
- **Care Schedules**: Receive personalized watering, fertilizing, and maintenance schedules

## 🛠️ Setup & Installation

### Prerequisites

- Python 3.7+
- Flask
- Google account (for Google Sheets API)

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/growvrd.git
   cd growvrd
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Google Sheets credentials (Optional - for production use)**
   - Create a project in Google Cloud Console
   - Enable Google Sheets API
   - Create credentials (OAuth client ID)
   - Download the credentials as `client_secrets.json` and place in project root
   
   *Note: The application will use mock data by default if credentials are not provided*

5. **Create a .env file in the project root**
   ```
   ENVIRONMENT=development
   USE_MOCK_DATA=true
   GROWVRD_TOKEN_PATH=token.pickle
   GROWVRD_CREDENTIALS_PATH=client_secrets.json
   ```

6. **Run the application**
   ```bash
   python start.py
   ```

7. **Access the application**
   - Web form interface: http://localhost:5001/
   - Chat interface: http://localhost:5001/chat

## 💬 Using the Chat Interface

The GrowVRD chat interface provides a conversational way to get plant recommendations. Here's a typical interaction:

1. Start with a greeting like "Hi" or "Hello"
2. Tell GrowVRD where you want to place plants (e.g., "I want plants for my living room")
3. Describe your light conditions (e.g., "It gets medium light" or "It has bright indirect sunlight")
4. Share your experience level (e.g., "I'm a beginner" or "I have intermediate experience")
5. Specify your maintenance preference (e.g., "I want low-maintenance plants")
6. Receive personalized plant recommendations!

You can also ask specific questions about plants, care requirements, or restart the conversation at any time.

## 🖥️ Using the Web Form Interface

The web form provides a structured approach to get plant recommendations:

1. Select your room location from the dropdown
2. Choose your experience level
3. Specify your maintenance preference
4. Select your light conditions
5. Click "Get Recommendations" to view your personalized suggestions

## 🌟 Subscription Features

GrowVRD offers different subscription tiers:

| Feature | Free | Subscriber |
|---------|------|------------|
| Basic recommendations | ✅ | ✅ |
| Custom plant kits | ❌ | ✅ |
| Detailed analytics | ❌ | ✅ |
| Service fee | 10% | 3% |
| Premium content | ❌ | ✅ |

## 🧑‍💻 Development

### Project Structure

```
GrowVRD/
├── .env                    # Environment variables
├── client_secrets.json     # Google API credentials
├── requirements.txt        # Dependencies
├── start.py                # Entry point script
├── app.py                  # Flask application
├── run.py                  # Run script
├── config.py               # Configuration
├── api_response.py         # API response formatting
├── api_security.py         # Security middleware
├── subscription_manager.py # Subscription features
├── static/                 # Frontend assets
│   ├── index.html          # Main page
│   ├── chat.html           # Chat interface
│   ├── style.css           # CSS styling
│   └── app.js              # Frontend JavaScript
├── data/                   # Data directory for TSV files
└── core/                   # Core functionality
    ├── data_handler.py     # Data parsing and validation
    ├── filters.py          # Plant filtering algorithms
    ├── mock_data.py        # Mock data for development
    ├── oauth_sheets_connector.py  # Google Sheets connection
    └── recommendation_engine.py   # Recommendation logic
```

### Adding New Plants

Plants are stored in the `GrowVRD_Plants` Google Sheet or in TSV format in the `data` directory when using mock data. Each plant has the following fields:

- `id`: Unique identifier
- `name`: Plant name (snake_case)
- `scientific_name`: Scientific name
- `natural_sunlight_needs`: Light requirements
- `led_light_requirements`: LED light requirements
- `water_frequency_days`: Days between watering
- `humidity_preference`: Humidity needs
- `difficulty`: Numeric difficulty rating (1-10)
- And many more detailed attributes...

### API Endpoints

- `/api/recommendations`: Get plant, product, and kit recommendations
- `/api/chat`: Process chat messages and generate responses
- `/api/plants/<plant_id>`: Get details about a specific plant
- `/api/kits/custom`: Create and save custom plant kits (subscribers only)

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgements

- Plant data sourced from various horticultural resources
- Icons from [your-icon-source]
- Built with Flask, Google Sheets API, and other open-source technologies