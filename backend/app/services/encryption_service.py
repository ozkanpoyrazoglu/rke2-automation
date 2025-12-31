from cryptography.fernet import Fernet
import os
import base64

def get_encryption_key() -> bytes:
    """
    Get or generate encryption key for credentials
    """
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise ValueError("ENCRYPTION_KEY environment variable not set")

    # Ensure key is properly formatted
    try:
        return base64.urlsafe_b64decode(key)
    except:
        # If not base64, derive from string
        return base64.urlsafe_b64encode(key.encode()[:32].ljust(32, b'0'))

def encrypt_secret(plaintext: str) -> str:
    """
    Encrypt a secret (SSH key or password)
    """
    key = get_encryption_key()
    fernet = Fernet(base64.urlsafe_b64encode(key))
    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()

def decrypt_secret(encrypted: str) -> str:
    """
    Decrypt a secret
    """
    key = get_encryption_key()
    fernet = Fernet(base64.urlsafe_b64encode(key))
    decrypted = fernet.decrypt(encrypted.encode())
    return decrypted.decode()
