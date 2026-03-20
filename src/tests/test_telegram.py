import json
from fastapi.testclient import TestClient
from main import app
from helpers.config import settings

# Override settings for testing
settings.telegram_secret_token = "test_telegram_secret_888"

client = TestClient(app)

def test_telegram_secure_payload_success():
    """Simulates Telegram sending a valid message with the correct secret token."""
    mock_payload = {"update_id": 12345, "message": {"text": "Hello bot!"}}
    
    headers = {"X-Telegram-Bot-Api-Secret-Token": "test_telegram_secret_888"}
    
    # We pass 'bot_001' as the identifier in the URL path
    response = client.post("/webhooks/telegram/bot_001", json=mock_payload, headers=headers)
    
    assert response.status_code == 200
    print("✅ Telegram Secure Payload Test Passed")

def test_telegram_secure_payload_spoofed():
    """Simulates a hacker guessing the URL but using the wrong secret token."""
    mock_payload = {"update_id": 99999, "message": {"text": "You are hacked!"}}
    
    # Provide an invalid token
    headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong_token_hacker"}
    
    response = client.post("/webhooks/telegram/bot_001", json=mock_payload, headers=headers)
    
    assert response.status_code == 403
    print("✅ Telegram Spoofed Payload (Security) Test Passed")

def test_telegram_missing_header():
    """Simulates a random internet scanner hitting the endpoint with no headers."""
    mock_payload = {"random_data": True}
    
    # No headers provided at all
    response = client.post("/webhooks/telegram/bot_001", json=mock_payload)
    
    assert response.status_code == 401
    print("✅ Telegram Missing Header (Security) Test Passed")

if __name__ == "__main__":
    print("Running Telegram Webhook Tests...")
    test_telegram_secure_payload_success()
    test_telegram_secure_payload_spoofed()
    test_telegram_missing_header()
    print("🎉 All Telegram tests passed!")