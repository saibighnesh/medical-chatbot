"""Unit tests for src/encryption.py"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.encryption as enc_module
from src.encryption import (
    EncryptionManager,
    decrypt_value,
    encrypt_value,
    get_encryption_manager,
    init_encryption,
    rotate_encryption_key,
)


class TestEncryptionManager:
    def test_init_default(self):
        mgr = EncryptionManager(secret_key="test-secret")
        assert mgr.secret_key == "test-secret"
        assert mgr.salt == b"medbot-encryption-salt-v1"

    def test_init_with_bytes_salt(self):
        mgr = EncryptionManager(secret_key="test-secret", salt=b"custom-salt-bytes")
        assert mgr.salt == b"custom-salt-bytes"

    def test_init_with_string_salt(self):
        mgr = EncryptionManager(secret_key="test-secret", salt="custom-salt-str")
        assert mgr.salt == b"custom-salt-str"

    def test_encrypt_returns_non_empty(self):
        mgr = EncryptionManager(secret_key="test-secret")
        result = mgr.encrypt("hello world")
        assert result != ""
        assert isinstance(result, str)

    def test_encrypt_empty_string_returns_empty(self):
        mgr = EncryptionManager(secret_key="test-secret")
        assert mgr.encrypt("") == ""

    def test_decrypt_roundtrip(self):
        mgr = EncryptionManager(secret_key="test-secret")
        plaintext = "my-api-key-12345"
        encrypted = mgr.encrypt(plaintext)
        assert mgr.decrypt(encrypted) == plaintext

    def test_decrypt_empty_string_returns_empty(self):
        mgr = EncryptionManager(secret_key="test-secret")
        assert mgr.decrypt("") == ""

    def test_decrypt_invalid_raises_value_error(self):
        mgr = EncryptionManager(secret_key="test-secret")
        with pytest.raises(ValueError, match="Decryption failed"):
            mgr.decrypt("not-valid-encrypted-data")

    def test_rotate_key_returns_new_manager(self):
        mgr = EncryptionManager(secret_key="old-secret")
        new_mgr = mgr.rotate_key("new-secret")
        assert isinstance(new_mgr, EncryptionManager)
        assert new_mgr.secret_key == "new-secret"
        # Salt is preserved across rotation
        assert new_mgr.salt == mgr.salt


class TestGlobalEncryptionFunctions:
    def setup_method(self):
        # Reset global state before each test
        enc_module._encryption_manager = None

    def test_init_encryption_creates_manager(self):
        mgr = init_encryption("global-secret")
        assert isinstance(mgr, EncryptionManager)
        assert enc_module._encryption_manager is mgr

    def test_get_encryption_manager_initializes_if_none(self):
        enc_module._encryption_manager = None
        mgr = get_encryption_manager()
        assert isinstance(mgr, EncryptionManager)

    def test_get_encryption_manager_returns_existing(self):
        existing = init_encryption("existing-secret")
        mgr = get_encryption_manager()
        assert mgr is existing

    def test_encrypt_value_and_decrypt_value_roundtrip(self):
        init_encryption("roundtrip-secret")
        plaintext = "test-api-key-abc123"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        assert decrypt_value(encrypted) == plaintext

    def test_rotate_encryption_key_updates_global(self):
        init_encryption("old-secret")
        new_mgr = rotate_encryption_key("new-secret")
        assert isinstance(new_mgr, EncryptionManager)
        assert enc_module._encryption_manager is new_mgr
        assert new_mgr.secret_key == "new-secret"
