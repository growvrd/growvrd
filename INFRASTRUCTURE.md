# AWS Infrastructure Setup

This document outlines the AWS infrastructure required for the GrowVRD application.

## AWS Services Used

1. **Amazon Cognito**
   - User authentication and management
   - JWT token generation and validation

2. **Amazon DynamoDB**
   - Primary data storage
   - Tables:
     - `Plants`: Plant information and care data
     - `Users`: User profiles and settings
     - `Subscriptions`: Subscription and payment information

3. **AWS IAM**
   - User roles and permissions
   - Service roles for application access to AWS resources

## Setup Instructions

### 1. AWS Account Setup

1. Sign in to the AWS Management Console
2. Create a new IAM user with programmatic access
3. Attach the following policies:
   - `AmazonDynamoDBFullAccess`
   - `AmazonCognitoPowerUser`
   - `AWSLambdaBasicExecutionRole` (if using Lambda)

### 2. Cognito User Pool Setup

1. Navigate to Amazon Cognito
2. Create a new User Pool
3. Configure attributes:
   - Email as username/alias
   - Enable email verification
   - Set password policy:
     - Minimum length: 8
     - Require numbers, uppercase, lowercase, and special characters
4. Create an App Client:
   - Generate client secret: Yes
   - Enable auth flows: ALLOW_USER_PASSWORD_AUTH, ALLOW_REFRESH_TOKEN_AUTH
   - Set token expiration:
     - Access token: 60 minutes
     - ID token: 60 minutes
     - Refresh token: 30 days

### 3. DynamoDB Tables

#### Plants Table
```
Table name: Plants
Partition key: id (String)
Sort key: N/A
Capacity mode: On-demand
```

#### Users Table
```
Table name: Users
Partition key: email (String)
Sort key: N/A
Capacity mode: On-demand
```

#### Subscriptions Table
```
Table name: Subscriptions
Partition key: user_id (String)
Sort key: subscription_id (String)
Capacity mode: On-demand
```

### 4. Environment Variables

Update your `.env` file with the following AWS-related variables:

```
# AWS Configuration
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=us-east-1

# Cognito Configuration
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
```

## Deployment

### Local Development
1. Set up the `.env` file with your AWS credentials
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `flask run`

### Production
1. Set up an EC2 instance or ECS cluster
2. Configure environment variables in your deployment platform
3. Set up a reverse proxy (Nginx/Apache) if needed
4. Configure HTTPS using AWS Certificate Manager

## Security Best Practices

1. **IAM Roles**: Use IAM roles instead of access keys when possible
2. **Secrets Management**: Use AWS Secrets Manager for production credentials
3. **Least Privilege**: Grant minimum required permissions to IAM users/roles
4. **Monitoring**: Enable CloudTrail and CloudWatch Logs
5. **Backup**: Set up DynamoDB backups

## Troubleshooting

- **Authentication Issues**: Verify Cognito user pool and app client settings
- **Permission Errors**: Check IAM policies and DynamoDB table permissions
- **Connection Issues**: Verify AWS region and credentials

## Cleanup

To avoid unnecessary charges, delete all AWS resources when not in use:
1. Delete DynamoDB tables
2. Delete Cognito user pool
3. Remove IAM users and policies
4. Clean up any other AWS resources created
