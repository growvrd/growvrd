#!/bin/bash

# Create AWS config directory if it doesn't exist
mkdir -p ~/.aws

# Create AWS config file
cat > ~/.aws/config <<EOL
[default]
region=${AWS_DEFAULT_REGION:-us-east-1}
output=json
EOL

# Create AWS credentials file
cat > ~/.aws/credentials <<EOL
[default]
aws_access_key_id=${AWS_ACCESS_KEY_ID}
aws_secret_access_key=${AWS_SECRET_ACCESS_KEY}
EOL

# Set permissions
chmod 600 ~/.aws/*

# Install Python dependencies
pip install -r requirements.txt

echo "✅ Replit setup complete!"
echo "🔑 AWS credentials configured"
echo "📦 Dependencies installed"
