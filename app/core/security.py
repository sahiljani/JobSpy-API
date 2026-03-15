import hmac
from hashlib import sha256


def generate_webhook_signature(secret: str, timestamp: str, raw_body: str) -> str:
    payload = f"{timestamp}.{raw_body}".encode('utf-8')
    digest = hmac.new(secret.encode('utf-8'), payload, sha256).hexdigest()
    return f"sha256={digest}"
