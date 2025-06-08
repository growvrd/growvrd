# test_aws_setup.py
"""
Test script to verify AWS infrastructure is working correctly
"""
import os
from dotenv import load_dotenv

load_dotenv()


def test_aws_connection():
    print("🧪 Testing GrowVRD AWS Infrastructure...")
    print("=" * 50)

    # Test environment variables
    print("1. Environment Variables:")
    aws_vars = [
        'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION',
        'DYNAMODB_PLANTS_TABLE', 'COGNITO_USER_POOL_ID', 'S3_BUCKET'
    ]

    for var in aws_vars:
        value = os.getenv(var)
        status = "✅" if value else "❌"
        print(f"   {status} {var}: {'Set' if value else 'Not set'}")

    print("\n2. Testing DynamoDB Connection:")
    try:
        from aws.dynamo_connector import DynamoConnector

        # Use the correct table prefix that matches your migrated tables
        dynamo = DynamoConnector(
            region_name=os.getenv('AWS_REGION'),
            table_prefix='growvrd-'  # Match your actual table prefix
        )

        # Override table name method to use full table names
        def get_full_table_name(table_type: str) -> str:
            table_map = {
                'plants': os.getenv('DYNAMODB_PLANTS_TABLE'),
                'products': os.getenv('DYNAMODB_PRODUCTS_TABLE'),
                'users': os.getenv('DYNAMODB_USERS_TABLE'),
                'kits': os.getenv('DYNAMODB_KITS_TABLE'),
                'plant_products': os.getenv('DYNAMODB_PLANT_PRODUCTS_TABLE'),
                'user_plants': os.getenv('DYNAMODB_USER_PLANTS_TABLE'),
                'local_vendors': os.getenv('DYNAMODB_LOCAL_VENDORS_TABLE')
            }
            return table_map.get(table_type, f"growvrd-{table_type}-development")

        dynamo._get_table_name = get_full_table_name

        # Test retrieving plants
        plants = dynamo.get_plants()
        print(f"   ✅ Retrieved {len(plants)} plants from DynamoDB")

        # Test retrieving products
        products = dynamo.get_products()
        print(f"   ✅ Retrieved {len(products)} products from DynamoDB")

        # Test retrieving users
        users = dynamo.get_users()
        print(f"   ✅ Retrieved {len(users)} users from DynamoDB")

    except Exception as e:
        print(f"   ❌ DynamoDB connection failed: {str(e)}")

    print("\n3. Testing S3 Connection:")
    try:
        import boto3
        s3 = boto3.client('s3')
        bucket_name = os.getenv('S3_BUCKET')

        # Test bucket access
        s3.head_bucket(Bucket=bucket_name)
        print(f"   ✅ S3 bucket '{bucket_name}' is accessible")

    except Exception as e:
        print(f"   ❌ S3 connection failed: {str(e)}")

    print("\n4. Testing Cognito Connection:")
    try:
        import boto3
        cognito = boto3.client('cognito-idp')
        user_pool_id = os.getenv('COGNITO_USER_POOL_ID')

        # Test user pool access
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        pool_name = response['UserPool']['Name']
        print(f"   ✅ Cognito User Pool '{pool_name}' is accessible")

    except Exception as e:
        print(f"   ❌ Cognito connection failed: {str(e)}")

    print("\n" + "=" * 50)
    print("🎉 AWS Infrastructure Test Complete!")
    print("\nNext steps:")
    print("1. Update your app to use DynamoDB instead of Google Sheets")
    print("2. Test your web application with the new AWS backend")
    print("3. Monitor performance and costs in AWS Console")


if __name__ == "__main__":
    test_aws_connection()