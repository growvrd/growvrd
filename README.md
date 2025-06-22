# 🌱 GrowVRD - Smart Plant Management System

GrowVRD is a comprehensive plant care and management platform that helps users track, manage, and optimize their plant care routines. The application provides personalized care recommendations, subscription-based premium features, and a seamless user experience.

## ✨ Features

- **🌿 Plant Management**: Track all your plants in one place
- **🔔 Smart Reminders**: Get notified when it's time to water or care for your plants
- **📊 Analytics**: Track plant growth and health over time
- **🤖 AI Assistant**: Get personalized plant care advice powered by OpenAI
- **🔒 Secure Authentication**: Powered by AWS Cognito
- **💳 Subscription Plans**: Premium features with Stripe integration
- **🌐 Responsive Design**: Works on desktop and mobile devices

## 🛠 Tech Stack

- **Backend**: Python 3.11, Flask
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Database**: AWS DynamoDB
- **Authentication**: AWS Cognito
- **Payments**: Stripe
- **AI**: OpenAI GPT Integration
- **APIs**: Perenual Plant API
- **Infrastructure**: AWS (DynamoDB, Cognito, IAM)
- **Deployment**: Replit (Development), AWS (Production)

## 💻 Local Development

### Prerequisites
- Python 3.11+
- Git
- AWS Account with appropriate permissions
- Stripe Account
- OpenAI API Key
- Perenual API Key

### Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/GrowVRD.git
   cd GrowVRD
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   Copy `.env.example` to `.env` and update with your credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

5. **Run the application**:
   ```bash
   flask run
   ```
   The app will be available at `http://localhost:5000`

## 🧪 Testing

Run the test suite with:
```bash
pytest
```

## 🏗 Project Structure

```
GrowVRD/
├── app.py                 # Main application entry point
├── requirements.txt       # Python dependencies
├── .env.example          # Example environment variables
├── .gitignore            # Git ignore rules
├── README.md             # This file
├── INFRASTRUCTURE.md     # AWS infrastructure documentation
├── static/               # Static files (CSS, JS, images)
│   ├── css/             # Stylesheets
│   ├── js/              # JavaScript files
│   └── images/          # Image assets
├── services/             # Business logic and services
│   ├── auth_service.py   # Authentication logic
│   ├── plant_service.py  # Plant management logic
│   ├── payment_service.py # Stripe integration
│   └── chat/            # AI chat functionality
└── tests/               # Test files
    ├── test_api.py      # API endpoint tests
    └── test_models.py   # Model tests
```

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋‍♂️ Support

For support, please open an issue in the GitHub repository or contact the maintainers.

## 🔗 Related Projects

- [Perenual API](https://perenual.com/)
- [Stripe API](https://stripe.com/docs/api)
- [OpenAI API](https://platform.openai.com/docs/)
- [AWS Cognito](https://aws.amazon.com/cognito/)

## 📚 Documentation

- [API Documentation](#) (Coming Soon)
- [Developer Guide](#) (Coming Soon)
- [Architecture Decision Records](#) (Coming Soon)

## 🚀 Quick Start (Replit)

1. **Fork this repository** to your GitHub account
2. **Import to Replit**:
   - Go to [Replit](https://replit.com)
   - Click "+" and select "Import from GitHub"
   - Enter your forked repository URL
   - Click "Import from GitHub"

3. **Configure Environment Variables**:
   - In Replit, click on the lock icon (🔒) in the left sidebar
   - Add the following secrets:
     - `AWS_ACCESS_KEY_ID`: Your AWS access key
     - `AWS_SECRET_ACCESS_KEY`: Your AWS secret key
     - `AWS_DEFAULT_REGION`: Your AWS region (e.g., `us-east-1`)
     - `COGNITO_USER_POOL_ID`: Your Cognito User Pool ID
     - `COGNITO_CLIENT_ID`: Your Cognito App Client ID
     - `FLASK_SECRET_KEY`: A secure secret key for Flask sessions

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the Application**:
   - Click the "Run" button in Replit
   - The app will be available at the URL shown in the Replit console

## 🛠️ Local Development

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/GrowVRD.git
   cd GrowVRD
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   Create a `.env` file in the root directory with:
   ```
   FLASK_APP=app.py
   FLASK_ENV=development
   AWS_ACCESS_KEY_ID=your_access_key
   AWS_SECRET_ACCESS_KEY=your_secret_key
   AWS_DEFAULT_REGION=us-east-1
   COGNITO_USER_POOL_ID=your_user_pool_id
   COGNITO_CLIENT_ID=your_client_id
   FLASK_SECRET_KEY=your_secret_key
   ```

5. **Run the application**:
   ```bash
   flask run
   ```
   The app will be available at `http://localhost:5000`

## 🌱 Project Structure

```
GrowVRD/
├── app.py                 # Main application entry point
├── requirements.txt       # Python dependencies
├── .replit                # Replit configuration
├── replit.nix             # Nix package configuration
├── .gitignore             # Git ignore rules
├── README.md              # This file
├── static/               # Static files (CSS, JS, images)
├── services/             # Business logic and services
└── tests/                # Test files
```

## 🔧 Dependencies

- Python 3.11+
- Flask
- Boto3 (AWS SDK)
- python-dotenv
- Other dependencies listed in `requirements.txt`

## 🏗️ Infrastructure

For detailed AWS infrastructure setup and configuration, see [INFRASTRUCTURE.md](INFRASTRUCTURE.md).

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
