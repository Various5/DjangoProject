import os
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Encryption key
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

if not ENCRYPTION_KEY:
    raise ValueError("No ENCRYPTION_KEY found in environment variables. Please set it in your .env file or environment.")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_password(password):
    """Encrypt a plaintext password."""
    return cipher_suite.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    """Decrypt an encrypted password."""
    try:
        return cipher_suite.decrypt(encrypted_password.encode()).decode()
    except (InvalidToken, AttributeError):
        return None
