"""
Encryption Module for API Key Management
Uses Fernet symmetric encryption with key derivation from Flask SECRET_KEY
"""

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionManager:
    """Manages encryption/decryption of sensitive data like API keys"""

    def __init__(self, secret_key=None, salt=None):
        """
        Initialize encryption manager

        Args:
            secret_key: Flask SECRET_KEY or custom key for derivation
            salt: Salt for key derivation (generated if not provided)
        """
        self.secret_key = secret_key or os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

        # Use provided salt or generate a new one
        if salt:
            self.salt = salt if isinstance(salt, bytes) else salt.encode()
        else:
            self.salt = b"medbot-encryption-salt-v1"  # Fixed salt for consistency

        # Derive encryption key from secret
        self.encryption_key = self._derive_key()
        self.cipher = Fernet(self.encryption_key)

    def _derive_key(self):
        """Derive a Fernet key from SECRET_KEY using PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=self.salt, iterations=100000, backend=default_backend()
        )
        key_material = kdf.derive(self.secret_key.encode())
        return base64.urlsafe_b64encode(key_material)

    def encrypt(self, plaintext):
        """
        Encrypt plaintext string

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted string (base64 encoded)
        """
        if not plaintext:
            return ""

        encrypted_bytes = self.cipher.encrypt(plaintext.encode())
        return encrypted_bytes.decode()

    def decrypt(self, encrypted_text):
        """
        Decrypt encrypted string

        Args:
            encrypted_text: Encrypted string to decrypt

        Returns:
            Decrypted plaintext string
        """
        if not encrypted_text:
            return ""

        try:
            decrypted_bytes = self.cipher.decrypt(encrypted_text.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")

    def rotate_key(self, new_secret_key):
        """
        Rotate encryption key (for re-encrypting data with new key)

        Args:
            new_secret_key: New SECRET_KEY to use

        Returns:
            New EncryptionManager instance with new key
        """
        return EncryptionManager(secret_key=new_secret_key, salt=self.salt)


# Global instance (initialized with app SECRET_KEY)
_encryption_manager = None


def init_encryption(secret_key=None):
    """Initialize global encryption manager"""
    global _encryption_manager
    _encryption_manager = EncryptionManager(secret_key=secret_key)
    return _encryption_manager


def get_encryption_manager():
    """Get global encryption manager instance"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager


# Convenience functions
def encrypt_value(plaintext):
    """Encrypt a value using global encryption manager"""
    return get_encryption_manager().encrypt(plaintext)


def decrypt_value(encrypted_text):
    """Decrypt a value using global encryption manager"""
    return get_encryption_manager().decrypt(encrypted_text)


def rotate_encryption_key(new_secret_key):
    """Rotate to a new encryption key"""
    global _encryption_manager
    _encryption_manager = EncryptionManager(secret_key=new_secret_key)
    return _encryption_manager
