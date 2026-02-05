#!/usr/bin/env python3
"""
Test API endpoints for conversation retrieval with proper authentication

SECURITY NOTE: Do NOT hardcode secrets in this file!
Set environment variables before running tests:
  export BUFFETT_JWT_SECRET="your-jwt-secret-from-aws-secrets-manager"

NOTE: These are integration tests that require a deployed API endpoint and JWT secret.
"""
import os
import requests
import json
import jwt
import pytest
from datetime import datetime, timedelta

# API Configuration
# NOTE: Set these environment variables before running tests:
#   export BUFFETT_API_BASE_URL="https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev"
#   export BUFFETT_JWT_SECRET="your-jwt-secret-from-aws-secrets-manager"
#   export BUFFETT_TEST_USER_ID="your-test-user-id"
API_BASE_URL = os.environ.get("BUFFETT_API_BASE_URL", "https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev")
TEST_JWT_SECRET = os.environ.get("BUFFETT_JWT_SECRET")
TEST_USER_ID = os.environ.get("BUFFETT_TEST_USER_ID", "109099666789991076125")

# Skip decorator for tests requiring JWT secret
requires_jwt_secret = pytest.mark.skipif(
    not TEST_JWT_SECRET,
    reason="BUFFETT_JWT_SECRET environment variable not set"
)

def create_test_jwt(user_id: str, email: str = "test@example.com", expires_in_minutes: int = 30) -> str:
    """Create a test JWT token for API testing"""
    if not TEST_JWT_SECRET:
        raise ValueError(
            "BUFFETT_JWT_SECRET environment variable not set. "
            "Get the JWT secret from AWS Secrets Manager (buffett-dev-jwt-secret) and set it: "
            "export BUFFETT_JWT_SECRET='your-secret-here'"
        )

    # Use a fixed timestamp from an hour ago to avoid any clock sync issues
    import time
    current_unix_time = int(time.time())
    issued_time = current_unix_time - 3600  # 1 hour ago
    expires_time = current_unix_time + (expires_in_minutes * 60)  # Future expiry

    payload = {
        'user_id': user_id,
        'email': email,
        'iat': issued_time,
        'exp': expires_time,
        'iss': 'buffett-chat-test'
    }

    print(f"  Debug: Current Unix time: {current_unix_time}")
    print(f"  Debug: JWT iat (issued): {issued_time}")
    print(f"  Debug: JWT exp (expires): {expires_time}")

    return jwt.encode(payload, TEST_JWT_SECRET, algorithm='HS256')

def test_options_request():
    """Test OPTIONS preflight request"""
    print("🔍 Testing OPTIONS preflight request...")

    try:
        response = requests.options(
            f"{API_BASE_URL}/conversations",
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Authorization,Content-Type'
            },
            timeout=10
        )

        print(f"  Status Code: {response.status_code}")
        print(f"  Headers: {dict(response.headers)}")

        if response.status_code == 200:
            print("  ✅ OPTIONS request successful!")
            # Check CORS headers
            cors_headers = {
                'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
                'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
                'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers')
            }
            print(f"  CORS Headers: {cors_headers}")
            return True
        else:
            print(f"  ❌ OPTIONS request failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False

    except Exception as e:
        print(f"  ❌ OPTIONS request error: {e}")
        return False

def test_conversations_without_auth():
    """Test GET /conversations without authorization"""
    print("\n🔍 Testing GET /conversations without authorization...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/conversations",
            timeout=10
        )

        print(f"  Status Code: {response.status_code}")
        print(f"  Response: {response.text[:200]}...")

        if response.status_code == 401 or response.status_code == 403:
            print("  ✅ Correctly denied access without authorization!")
            return True
        else:
            print(f"  ⚠️  Expected 401/403, got {response.status_code}")
            return False

    except Exception as e:
        print(f"  ❌ Request error: {e}")
        return False

@requires_jwt_secret
@pytest.mark.integration
def test_conversations_with_auth():
    """Test GET /conversations with valid JWT authorization"""
    print("\n🔍 Testing GET /conversations with JWT authorization...")

    # Create JWT token
    token = create_test_jwt(TEST_USER_ID)
    print(f"  Using JWT for user_id: {TEST_USER_ID}")

    try:
        response = requests.get(
            f"{API_BASE_URL}/conversations",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            timeout=10
        )

        print(f"  Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Successfully retrieved conversations!")
            print(f"  Conversation count: {data.get('count', 0)}")

            conversations = data.get('conversations', [])
            if conversations:
                print(f"  Sample conversation:")
                conv = conversations[0]
                print(f"    - ID: {conv.get('conversation_id')}")
                print(f"    - User ID: {conv.get('user_id')}")
                print(f"    - Title: {conv.get('title')}")
                print(f"    - Message Count: {conv.get('message_count')}")
                print(f"    - Updated: {conv.get('updated_at')}")

            return True, conversations
        else:
            print(f"  ❌ Request failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False, []

    except Exception as e:
        print(f"  ❌ Request error: {e}")
        return False, []

def _test_conversation_messages(conversation_id: str):
    """Helper: Test GET /conversations/{id}/messages with authorization.

    Note: This is a helper function, not a standalone test.
    It requires a conversation_id parameter and is called by run_all_tests.
    """
    print(f"\n🔍 Testing GET /conversations/{conversation_id}/messages...")

    # Create JWT token
    token = create_test_jwt(TEST_USER_ID)

    try:
        response = requests.get(
            f"{API_BASE_URL}/conversations/{conversation_id}/messages",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            timeout=10
        )

        print(f"  Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Successfully retrieved messages!")
            print(f"  Message count: {data.get('count', 0)}")

            messages = data.get('messages', [])
            if messages:
                print(f"  Sample messages:")
                for i, msg in enumerate(messages[:2], 1):
                    print(f"    Message {i}:")
                    print(f"      - ID: {msg.get('message_id')}")
                    print(f"      - Type: {msg.get('message_type')}")
                    print(f"      - User ID: {msg.get('user_id')}")
                    print(f"      - Content: {msg.get('content', '')[:50]}...")

            return True
        else:
            print(f"  ❌ Request failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False

    except Exception as e:
        print(f"  ❌ Request error: {e}")
        return False

def main():
    """Run API endpoint tests"""
    print("=" * 70)
    print("🧪 API Endpoint Tests")
    print("=" * 70)

    # Test 1: OPTIONS preflight
    test1_result = test_options_request()

    # Test 2: No auth
    test2_result = test_conversations_without_auth()

    # Test 3: With auth
    test3_result, conversations = test_conversations_with_auth()

    # Test 4: Message retrieval (if we have conversations)
    test4_result = True
    if test3_result and conversations:
        conversation_id = conversations[0]['conversation_id']
        test4_result = _test_conversation_messages(conversation_id)
    else:
        print(f"\n⚠️  Skipping message test - no conversations available")

    # Summary
    print("\n" + "=" * 70)
    print("📊 Test Results Summary")
    print("=" * 70)
    print(f"OPTIONS Preflight:       {'✅ PASS' if test1_result else '❌ FAIL'}")
    print(f"No Auth (Expected Deny): {'✅ PASS' if test2_result else '❌ FAIL'}")
    print(f"With JWT Auth:           {'✅ PASS' if test3_result else '❌ FAIL'}")
    print(f"Message Retrieval:       {'✅ PASS' if test4_result else '❌ FAIL'}")

    if all([test1_result, test2_result, test3_result, test4_result]):
        print("\n🎉 All API tests passed! The backend is ready for frontend integration.")
        return True
    else:
        print("\n⚠️  Some API tests failed. Check the logs above for details.")
        return False

if __name__ == "__main__":
    # Install required dependencies
    try:
        import jwt
        import requests
    except ImportError:
        print("Installing required dependencies...")
        import subprocess
        subprocess.check_call(["pip", "install", "PyJWT", "requests"])
        import jwt
        import requests

    # Run tests
    result = main()
    exit(0 if result else 1)