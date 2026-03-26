"""Unit tests for src/database.py using a temporary SQLite database."""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Shared DB fixture — creates a fresh temp database for each test
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a fresh temporary SQLite DB and patch DB_PATH for all database calls."""
    db_file = str(tmp_path / "test.db")
    with patch("src.database.DB_PATH", db_file):
        import src.database as db_module

        db_module.init_db()
        yield db_module


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_creates_tables(self, tmp_db):
        import sqlite3

        conn = sqlite3.connect(tmp_db.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "users" in tables
        assert "chat_history" in tables
        assert "api_keys" in tables
        assert "documents" in tables
        assert "settings" in tables
        assert "audit_log" in tables

    def test_idempotent(self, tmp_db):
        # Calling init_db twice should not raise
        tmp_db.init_db()
        tmp_db.init_db()


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class TestUser:
    def test_create_user(self, tmp_db):
        user = tmp_db.User.create("alice", "alice@example.com", "Password1!")
        assert user is not None
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.id > 0

    def test_create_duplicate_username(self, tmp_db):
        tmp_db.User.create("bob", "bob@example.com", "Password1!")
        duplicate = tmp_db.User.create("bob", "bob2@example.com", "Password1!")
        assert duplicate is None

    def test_create_duplicate_email(self, tmp_db):
        tmp_db.User.create("carol", "carol@example.com", "Password1!")
        duplicate = tmp_db.User.create("carol2", "carol@example.com", "Password1!")
        assert duplicate is None

    def test_get_by_id(self, tmp_db):
        created = tmp_db.User.create("dave", "dave@example.com", "Password1!")
        fetched = tmp_db.User.get(created.id)
        assert fetched is not None
        assert fetched.username == "dave"

    def test_get_nonexistent_id(self, tmp_db):
        assert tmp_db.User.get(99999) is None

    def test_get_by_username(self, tmp_db):
        tmp_db.User.create("eve", "eve@example.com", "Password1!")
        user = tmp_db.User.get_by_username("eve")
        assert user is not None
        assert user.email == "eve@example.com"

    def test_get_by_username_not_found(self, tmp_db):
        assert tmp_db.User.get_by_username("nobody") is None

    def test_verify_password_correct(self, tmp_db):
        tmp_db.User.create("frank", "frank@example.com", "MyPass123")
        assert tmp_db.User.verify_password("frank", "MyPass123") is True

    def test_verify_password_wrong(self, tmp_db):
        tmp_db.User.create("grace", "grace@example.com", "MyPass123")
        assert tmp_db.User.verify_password("grace", "WrongPass") is False

    def test_verify_password_unknown_user(self, tmp_db):
        assert tmp_db.User.verify_password("unknown", "any") is False

    def test_user_is_admin_default_false(self, tmp_db):
        user = tmp_db.User.create("henry", "henry@example.com", "Password1!")
        assert user.is_admin is False

    def test_user_get_id(self, tmp_db):
        user = tmp_db.User.create("ida", "ida@example.com", "Password1!")
        assert user.get_id() == str(user.id)

    def test_user_properties(self, tmp_db):
        user = tmp_db.User.create("jack", "jack@example.com", "Password1!")
        assert user.is_authenticated is True
        assert user.is_active is True
        assert user.is_anonymous is False


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------


class TestChatHistory:
    def test_save_and_retrieve(self, tmp_db):
        user = tmp_db.User.create("user1", "u1@example.com", "Pass1!")
        tmp_db.save_chat_history(user.id, "What is diabetes?", "Diabetes is a chronic condition.")
        history = tmp_db.get_chat_history(user.id)
        assert len(history) == 1
        assert history[0]["question"] == "What is diabetes?"
        assert history[0]["answer"] == "Diabetes is a chronic condition."

    def test_get_history_empty(self, tmp_db):
        user = tmp_db.User.create("user2", "u2@example.com", "Pass1!")
        history = tmp_db.get_chat_history(user.id)
        assert history == []

    def test_history_limit(self, tmp_db):
        user = tmp_db.User.create("user3", "u3@example.com", "Pass1!")
        for i in range(10):
            tmp_db.save_chat_history(user.id, f"Q{i}", f"A{i}")
        history = tmp_db.get_chat_history(user.id, limit=5)
        assert len(history) == 5

    def test_clear_history(self, tmp_db):
        user = tmp_db.User.create("user4", "u4@example.com", "Pass1!")
        tmp_db.save_chat_history(user.id, "Q1", "A1")
        tmp_db.save_chat_history(user.id, "Q2", "A2")
        result = tmp_db.clear_chat_history(user.id)
        assert result is True
        assert tmp_db.get_chat_history(user.id) == []

    def test_clear_history_returns_true_on_empty(self, tmp_db):
        user = tmp_db.User.create("user5", "u5@example.com", "Pass1!")
        assert tmp_db.clear_chat_history(user.id) is True


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


class TestApiKeys:
    def test_save_and_get_api_key(self, tmp_db):
        result = tmp_db.save_api_key("gemini", "test-api-key-12345")
        assert result is True
        key = tmp_db.get_api_key("gemini")
        assert key == "test-api-key-12345"

    def test_get_nonexistent_key(self, tmp_db):
        assert tmp_db.get_api_key("nonexistent") is None

    def test_update_existing_key(self, tmp_db):
        tmp_db.save_api_key("openai", "old-key")
        tmp_db.save_api_key("openai", "new-key")
        assert tmp_db.get_api_key("openai") == "new-key"

    def test_list_api_keys(self, tmp_db):
        tmp_db.save_api_key("gemini", "key1")
        tmp_db.save_api_key("openai", "key2")
        keys = tmp_db.list_api_keys()
        providers = [k["provider"] for k in keys]
        assert "gemini" in providers
        assert "openai" in providers

    def test_list_api_keys_with_preview(self, tmp_db):
        tmp_db.save_api_key("gemini", "test-api-key-12345")
        keys = tmp_db.list_api_keys(show_keys=True)
        for k in keys:
            if k["provider"] == "gemini":
                assert "key_preview" in k
                assert k["key_preview"].startswith("****")

    def test_delete_api_key(self, tmp_db):
        tmp_db.save_api_key("claude", "claude-key")
        result = tmp_db.delete_api_key("claude")
        assert result is True
        assert tmp_db.get_api_key("claude") is None

    def test_delete_nonexistent_key(self, tmp_db):
        result = tmp_db.delete_api_key("does_not_exist")
        assert result is True  # DELETE is idempotent

    def test_set_active_provider(self, tmp_db):
        tmp_db.save_api_key("gemini", "gemini-key")
        tmp_db.save_api_key("openai", "openai-key")
        result = tmp_db.set_active_provider("gemini")
        assert result is True
        active = tmp_db.get_active_provider()
        assert active is not None
        assert active["provider"] == "gemini"

    def test_get_active_provider_none(self, tmp_db):
        assert tmp_db.get_active_provider() is None

    def test_set_active_deactivates_others(self, tmp_db):
        tmp_db.save_api_key("gemini", "gemini-key", is_active=True)
        tmp_db.save_api_key("openai", "openai-key")
        tmp_db.set_active_provider("openai")
        active = tmp_db.get_active_provider()
        assert active["provider"] == "openai"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class TestDocuments:
    def test_save_and_get_document(self, tmp_db):
        doc_id = tmp_db.save_document_metadata("test.pdf", "Test.pdf", "/data/test.pdf", 1024, 5)
        assert doc_id is not None
        docs = tmp_db.get_all_documents()
        assert len(docs) == 1
        assert docs[0]["filename"] == "test.pdf"

    def test_get_document_by_id(self, tmp_db):
        doc_id = tmp_db.save_document_metadata("doc.pdf", "Doc.pdf", "/data/doc.pdf", 512, 3)
        doc = tmp_db.get_document_by_id(doc_id)
        assert doc is not None
        assert doc["original_name"] == "Doc.pdf"
        assert doc["page_count"] == 3

    def test_get_document_by_id_not_found(self, tmp_db):
        assert tmp_db.get_document_by_id(99999) is None

    def test_update_document_metadata(self, tmp_db):
        doc_id = tmp_db.save_document_metadata("upd.pdf", "Upd.pdf", "/data/upd.pdf", 100, 1)
        result = tmp_db.update_document(doc_id, is_active=False)
        assert result is True
        doc = tmp_db.get_document_by_id(doc_id)
        assert doc["is_active"] is False

    def test_update_document_no_valid_fields(self, tmp_db):
        doc_id = tmp_db.save_document_metadata("x.pdf", "x.pdf", "/x.pdf", 1, 1)
        result = tmp_db.update_document(doc_id, nonexistent_field="value")
        assert result is False

    def test_delete_document(self, tmp_db):
        doc_id = tmp_db.save_document_metadata("del.pdf", "Del.pdf", "/data/del.pdf", 100, 1)
        result = tmp_db.delete_document(doc_id)
        assert result is True
        assert tmp_db.get_document_by_id(doc_id) is None

    def test_get_all_documents_active_only(self, tmp_db):
        id1 = tmp_db.save_document_metadata("a.pdf", "A.pdf", "/a.pdf", 100, 1)
        id2 = tmp_db.save_document_metadata("b.pdf", "B.pdf", "/b.pdf", 100, 1)
        tmp_db.update_document(id2, is_active=False)
        active_docs = tmp_db.get_all_documents(active_only=True)
        assert len(active_docs) == 1
        assert active_docs[0]["id"] == id1

    def test_reorder_documents(self, tmp_db):
        id1 = tmp_db.save_document_metadata("r1.pdf", "R1.pdf", "/r1.pdf", 100, 1)
        id2 = tmp_db.save_document_metadata("r2.pdf", "R2.pdf", "/r2.pdf", 100, 1)
        result = tmp_db.reorder_documents([id2, id1])
        assert result is True
        docs = tmp_db.get_all_documents()
        assert docs[0]["id"] == id2
        assert docs[1]["id"] == id1

    def test_update_existing_document_resets_status(self, tmp_db):
        tmp_db.save_document_metadata("dup.pdf", "Dup.pdf", "/dup.pdf", 100, 1)
        tmp_db.save_document_metadata("dup.pdf", "Dup.pdf", "/dup.pdf", 200, 2)
        docs = tmp_db.get_all_documents()
        assert len(docs) == 1
        assert docs[0]["file_size"] == 200


# ---------------------------------------------------------------------------
# System Settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_set_and_get_setting(self, tmp_db):
        result = tmp_db.set_setting("theme", "dark")
        assert result is True
        assert tmp_db.get_setting("theme") == "dark"

    def test_get_nonexistent_setting_returns_default(self, tmp_db):
        assert tmp_db.get_setting("missing_key", default="fallback") == "fallback"

    def test_update_existing_setting(self, tmp_db):
        tmp_db.set_setting("theme", "light")
        tmp_db.set_setting("theme", "dark")
        assert tmp_db.get_setting("theme") == "dark"

    def test_get_nonexistent_returns_none(self, tmp_db):
        assert tmp_db.get_setting("nonexistent") is None


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_log_admin_action(self, tmp_db):
        user = tmp_db.User.create("admin", "admin@example.com", "Admin1!")
        result = tmp_db.log_admin_action(user.id, "reindex", "Rebuilt FAISS index", "127.0.0.1")
        assert result is True

    def test_log_action_without_details(self, tmp_db):
        user = tmp_db.User.create("admin2", "admin2@example.com", "Admin1!")
        result = tmp_db.log_admin_action(user.id, "login")
        assert result is True
