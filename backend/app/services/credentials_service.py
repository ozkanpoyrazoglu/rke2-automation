from app.services.encryption_service import decrypt_secret

def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt an encrypted password
    """
    return decrypt_secret(encrypted_password)
