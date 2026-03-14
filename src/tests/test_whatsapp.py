import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from main import app
from helpers.config import settings

# Override settings for testing purposes
settings.whatsapp_verify_token = "test_token_123"
settings.whatsapp_app_secret = "test_secret_abc"

client = TestClient(app)

def test_whatsapp_verification_success():
    """Simulates Meta sending the GET request to verify the webhook."""
    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": 1158201444,
            "hub.verify_token": "test_token_123"
        }
    )
    assert response.status_code == 200
    assert response.text == "1158201444"
    print("✅ GET Verification Test Passed")

def test_whatsapp_verification_failure():
    """Simulates a hacker guessing the verification URL with a bad token."""
    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": 1158201444,
            "hub.verify_token": "wrong_token"
        }
    )
    assert response.status_code == 403
    print("✅ GET Verification Failure (Security) Test Passed")

def test_whatsapp_secure_payload_success():
    """Simulates Meta sending a valid chat message with a correct signature."""
    mock_payload = {"object": "whatsapp_business_account", "entry": [{"id": "123"}]}
    raw_body = json.dumps(mock_payload).encode("utf-8")
    
    # Generate the signature exactly like Meta does
    signature = hmac.new(
        key=b"test_secret_abc",
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    headers = {"X-Hub-Signature-256": f"sha256={signature}"}
    
    response = client.post("/webhooks/whatsapp", content=raw_body, headers=headers)
    assert response.status_code == 200
    print("✅ POST Secure Payload Test Passed")

def test_whatsapp_secure_payload_spoofed():
    """Simulates a malicious user sending a fake message with a bad signature."""
    mock_payload = {"object": "whatsapp_business_account", "entry": [{"id": "HACKER"}]}
    raw_body = json.dumps(mock_payload).encode("utf-8")
    
    # Provide an invalid signature
    headers = {"X-Hub-Signature-256": "sha256=fake_signature_99999"}
    
    response = client.post("/webhooks/whatsapp", content=raw_body, headers=headers)
    assert response.status_code == 403
    print("✅ POST Spoofed Payload (Security) Test Passed")

if __name__ == "__main__":
    print("Running WhatsApp Webhook Tests...")
    test_whatsapp_verification_success()
    test_whatsapp_verification_failure()
    test_whatsapp_secure_payload_success()
    test_whatsapp_secure_payload_spoofed()
    print("🎉 All tests passed beautifully!")