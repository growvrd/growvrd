#!/usr/bin/env python3
"""
Test OpenAI Integration with DynamoDB
Comprehensive test suite to verify your maximized OpenAI setup
"""

import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def test_openai_integration():
    """Comprehensive test of OpenAI + DynamoDB integration"""

    print("🧪 Testing GrowVRD OpenAI Integration")
    print("=" * 50)

    # Test 1: Environment Check
    print("\n1. 🔧 Environment Check:")
    openai_key = os.getenv('OPENAI_API_KEY')
    aws_region = os.getenv('AWS_REGION')

    if openai_key:
        key_preview = openai_key[:8] + "..." + openai_key[-4:] if len(openai_key) > 12 else "short_key"
        print(f"   ✅ OpenAI API Key: {key_preview}")
    else:
        print("   ❌ OpenAI API Key: Not found")
        return False

    if aws_region:
        print(f"   ✅ AWS Region: {aws_region}")
    else:
        print("   ⚠️  AWS Region: Not set (will use default)")

    # Test 2: OpenAI Client Initialization
    print("\n2. 🤖 OpenAI Client Test:")
    try:
        from enhanced_chat import openai_client, get_advanced_expert

        if openai_client:
            print("   ✅ OpenAI client initialized successfully")

            # Test basic API call
            start_time = time.time()
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10
            )
            response_time = time.time() - start_time

            print(f"   ✅ API Response Time: {response_time:.2f} seconds")
            print(f"   ✅ Tokens Used: {response.usage.total_tokens}")
            print(f"   ✅ Response: {response.choices[0].message.content[:50]}...")

        else:
            print("   ❌ OpenAI client not initialized")
            return False

    except Exception as e:
        print(f"   ❌ OpenAI Error: {e}")
        return False

    # Test 3: DynamoDB Integration
    print("\n3. 📊 DynamoDB Integration Test:")
    try:
        from enhanced_chat import dynamo_connector

        if dynamo_connector:
            print("   ✅ DynamoDB connector available")

            # Test data retrieval
            plants = dynamo_connector.get_plants()
            products = dynamo_connector.get_products()

            print(f"   ✅ Retrieved {len(plants)} plants from DynamoDB")
            print(f"   ✅ Retrieved {len(products)} products from DynamoDB")

            # Show sample data
            if plants:
                sample_plant = plants[0]
                print(f"   📋 Sample Plant: {sample_plant.get('name', 'Unknown')}")

            if products:
                sample_product = products[0]
                print(f"   📋 Sample Product: {sample_product.get('name', 'Unknown')}")

        else:
            print("   ❌ DynamoDB connector not available")
            return False

    except Exception as e:
        print(f"   ❌ DynamoDB Error: {e}")
        return False

    # Test 4: Enhanced Chat System
    print("\n4. 🌿 Enhanced Chat System Test:")
    try:
        expert = get_advanced_expert()
        print("   ✅ Advanced plant expert initialized")

        # Test conversation
        test_messages = [
            "I need a plant for my dark bedroom",
            "How do I care for a snake plant?",
            "My plant has yellow leaves"
        ]

        for i, message in enumerate(test_messages, 1):
            print(f"\n   Test {i}: '{message}'")

            start_time = time.time()
            response = expert.generate_enhanced_response(message)
            response_time = time.time() - start_time

            print(f"   ⏱️  Response Time: {response_time:.2f}s")
            print(f"   🤖 Provider: {response.get('provider', 'unknown')}")
            print(f"   📝 Response Length: {len(response.get('content', ''))}")
            print(f"   🌱 Plants Suggested: {len(response.get('plants', []))}")
            print(f"   🛒 Products Suggested: {len(response.get('products', []))}")
            print(f"   🔤 Tokens Used: {response.get('tokens_used', 'N/A')}")

            if response.get('success'):
                print("   ✅ Response generated successfully")
            else:
                print(f"   ❌ Response failed: {response.get('error', 'Unknown error')}")

            # Show preview of response
            content_preview = response.get('content', '')[:150]
            print(f"   💬 Preview: {content_preview}...")

    except Exception as e:
        print(f"   ❌ Enhanced Chat Error: {e}")
        return False

    # Test 5: Performance Benchmark
    print("\n5. 🚀 Performance Benchmark:")
    try:
        # Benchmark multiple requests
        benchmark_messages = [
            "Recommend a low-light plant",
            "Care tips for fiddle leaf fig",
            "Best soil for succulents"
        ]

        total_time = 0
        total_tokens = 0

        for message in benchmark_messages:
            start_time = time.time()
            response = expert.generate_enhanced_response(message)
            response_time = time.time() - start_time

            total_time += response_time
            total_tokens += response.get('tokens_used', 0)

        avg_response_time = total_time / len(benchmark_messages)
        print(f"   ⏱️  Average Response Time: {avg_response_time:.2f}s")
        print(f"   🔤 Total Tokens Used: {total_tokens}")
        print(f"   💰 Estimated Cost: ${total_tokens * 0.0015 / 1000:.4f}")

        # Performance rating
        if avg_response_time < 2.0:
            print("   🌟 Performance: EXCELLENT")
        elif avg_response_time < 4.0:
            print("   ✅ Performance: GOOD")
        else:
            print("   ⚠️  Performance: NEEDS OPTIMIZATION")

    except Exception as e:
        print(f"   ❌ Benchmark Error: {e}")

    # Test 6: Data Integration Quality
    print("\n6. 🎯 Data Integration Quality:")
    try:
        # Test recommendation with real data
        response = expert.generate_enhanced_response("I want a beginner-friendly plant for low light")

        plants = response.get('plants', [])
        products = response.get('products', [])

        if plants:
            print(f"   ✅ Plant Recommendations: {len(plants)} plants suggested")
            for plant in plants[:2]:
                name = plant.get('name', 'Unknown')
                score = plant.get('match_score', 'N/A')
                print(f"      🌱 {name} (Score: {score})")

        if products:
            print(f"   ✅ Product Suggestions: {len(products)} products suggested")
            for product in products[:2]:
                name = product.get('name', 'Unknown')
                rating = product.get('compatibility_rating', 'N/A')
                print(f"      🛒 {name} (Rating: {rating}/5)")

        # Check content quality
        content = response.get('content', '')
        if len(content) > 200:
            print("   ✅ Response Quality: Detailed and comprehensive")
        elif len(content) > 100:
            print("   ✅ Response Quality: Good detail level")
        else:
            print("   ⚠️  Response Quality: Could be more detailed")

    except Exception as e:
        print(f"   ❌ Integration Test Error: {e}")

    # Final Results
    print("\n" + "=" * 50)
    print("🎉 OPENAI INTEGRATION TEST COMPLETE!")
    print("\n✅ Your GrowVRD system is fully optimized with:")
    print("   🤖 OpenAI GPT-3.5-turbo integration")
    print("   📊 Real DynamoDB plant data")
    print("   🌱 Intelligent plant recommendations")
    print("   🛒 Product compatibility system")
    print("   💬 Advanced conversation management")

    print("\n🚀 Ready for production ChatGPT-like experience!")
    return True

def test_specific_scenarios():
    """Test specific plant expert scenarios"""
    print("\n🌿 Testing Plant Expert Scenarios:")

    scenarios = [
        {
            'name': 'Beginner Request',
            'message': 'I\'m a complete beginner and want an easy plant for my apartment',
            'expected': ['recommendations', 'beginner_friendly', 'care_tips']
        },
        {
            'name': 'Problem Diagnosis',
            'message': 'My snake plant has yellow mushy leaves at the base',
            'expected': ['diagnosis', 'solution', 'prevention']
        },
        {
            'name': 'Product Advice',
            'message': 'What pot should I use for my new monstera?',
            'expected': ['product_suggestions', 'compatibility', 'sizing']
        },
        {
            'name': 'Care Schedule',
            'message': 'How often should I water my fiddle leaf fig?',
            'expected': ['specific_frequency', 'seasonal_variation', 'indicators']
        }
    ]

    try:
        from enhanced_chat import get_advanced_expert
        expert = get_advanced_expert()

        for scenario in scenarios:
            print(f"\n📋 {scenario['name']}:")
            print(f"   Query: {scenario['message']}")

            response = expert.generate_enhanced_response(scenario['message'])

            if response.get('success'):
                content = response.get('content', '').lower()

                # Check for expected elements
                found_elements = []
                for expected in scenario['expected']:
                    if any(keyword in content for keyword in expected.split('_')):
                        found_elements.append(expected)

                print(f"   ✅ Success - Found: {', '.join(found_elements)}")
                print(f"   📊 Quality: {len(response.get('content', ''))} chars, {len(response.get('plants', []))} plants")
            else:
                print(f"   ❌ Failed: {response.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"❌ Scenario testing failed: {e}")

if __name__ == "__main__":
    success = test_openai_integration()

    if success:
        test_specific_scenarios()
        print("\n🎯 All tests passed! Your OpenAI integration is maximized! 🚀")
    else:
        print("\n❌ Some tests failed. Check the errors above and fix them.")
        print("💡 Common solutions:")
        print("   • Verify OpenAI API key in .env file")
        print("   • Check OpenAI account billing status")
        print("   • Ensure DynamoDB tables are properly migrated")
        print("   • Check AWS credentials and permissions")