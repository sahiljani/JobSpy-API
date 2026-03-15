import base64
import hashlib
import hmac
from hashlib import sha256

from cryptography.fernet import Fernet


def generate_webhook_signature(secret: str, timestamp: str, raw_body: str) -> str:
    payload = f"{timestamp}.{raw_body}".encode('utf-8')
    digest = hmac.new(secret.encode('utf-8'), payload, sha256).hexdigest()
    return f"sha256={digest}"


def _derive_fernet_key(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plain_text: str, seed: str) -> str:
    f = Fernet(_derive_fernet_key(seed))
    return f.encrypt(plain_text.encode('utf-8')).decode('utf-8')


def decrypt_secret(cipher_text: str, seed: str) -> str:
    f = Fernet(_derive_fernet_key(seed))
    return f.decrypt(cipher_text.encode('utf-8')).decode('utf-8')
