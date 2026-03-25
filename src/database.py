import logging
import os
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from src.encryption import decrypt_value, encrypt_value

_log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "users.db")


def _connect():
    """Open a SQLite connection with sane production defaults."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database with all required tables"""
    conn = _connect()
    conn.execute("PRAGMA synchronous=NORMAL")  # Safe with WAL; faster than FULL
    cursor = conn.cursor()

    # Users table with is_admin column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Chat history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # API keys table for storing encrypted LLM provider credentials
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT UNIQUE NOT NULL,
            api_key_encrypted TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Documents metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            page_count INTEGER DEFAULT 0,
            display_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending_index',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create index on filename and is_active for fast lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_filename
        ON documents(filename)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_active
        ON documents(is_active)
    """)

    # System settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Audit log table for tracking admin actions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            action_details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()

    # Migration: Add is_admin column to existing users table if it doesn't exist
    try:
        cursor.execute("SELECT is_admin FROM users LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        conn.commit()

    conn.close()


class User:
    def __init__(self, id, username, email, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = bool(is_admin)
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return str(self.id)

    @staticmethod
    def get(user_id):
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, is_admin FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return User(result[0], result[1], result[2], result[3])
        return None

    @staticmethod
    def get_by_username(username):
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, is_admin FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return User(result[0], result[1], result[2], result[3])
        return None

    @staticmethod
    def create(username, email, password, is_admin=False):
        try:
            conn = _connect()
            cursor = conn.cursor()
            password_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                (username, email, password_hash, int(is_admin)),
            )
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return User(user_id, username, email, is_admin)
        except sqlite3.IntegrityError:
            return None

    @staticmethod
    def verify_password(username, password):
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()

        if result and check_password_hash(result[0], password):
            return True
        return False


def save_chat_history(user_id, question, answer):
    """Save chat interaction to history. Silently fails rather than crashing the SSE stream."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (user_id, question, answer) VALUES (?, ?, ?)", (user_id, question, answer)
        )
        conn.commit()
    except Exception as e:
        _log.error(f"Error saving chat history: {e}")
    finally:
        conn.close()


def get_chat_history(user_id, limit=50):
    """Retrieve chat history for a user"""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT question, answer, created_at FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    results = cursor.fetchall()
    conn.close()

    return [{"question": r[0], "answer": r[1], "created_at": r[2]} for r in reversed(results)]


def clear_chat_history(user_id):
    """Clear all chat history for a user."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error clearing chat history: {e}")
        return False
    finally:
        conn.close()


# ============================================================================
# API Keys Management Functions
# ============================================================================


def save_api_key(provider_name, api_key, is_active=False):
    """Save or update an API key for a provider."""
    conn = _connect()
    try:
        encrypted_key = encrypt_value(api_key)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM api_keys WHERE provider_name = ?", (provider_name,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE api_keys
                SET api_key_encrypted = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE provider_name = ?
            """,
                (encrypted_key, int(is_active), provider_name),
            )
        else:
            cursor.execute(
                """
                INSERT INTO api_keys (provider_name, api_key_encrypted, is_active)
                VALUES (?, ?, ?)
            """,
                (provider_name, encrypted_key, int(is_active)),
            )
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error saving API key: {e}")
        return False
    finally:
        conn.close()


def get_api_key(provider_name, decrypt=True):
    """Get API key for a provider."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT api_key_encrypted FROM api_keys WHERE provider_name = ?", (provider_name,))
        result = cursor.fetchone()
        if result and result[0]:
            return decrypt_value(result[0]) if decrypt else result[0]
        return None
    except Exception as e:
        _log.error(f"Error retrieving API key: {e}")
        return None
    finally:
        conn.close()


def list_api_keys(show_keys=False):
    """List all API keys."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT provider_name, api_key_encrypted, is_active, updated_at
            FROM api_keys
            ORDER BY provider_name
        """)
        results = cursor.fetchall()
        keys = []
        for row in results:
            provider, encrypted_key, is_active, updated_at = row
            key_info = {
                "provider": provider,
                "is_active": bool(is_active),
                "has_key": bool(encrypted_key),
                "updated_at": updated_at,
            }
            if show_keys and encrypted_key:
                try:
                    decrypted = decrypt_value(encrypted_key)
                    key_info["key_preview"] = "****" + decrypted[-4:] if len(decrypted) > 4 else "****"
                except Exception:
                    key_info["key_preview"] = "****"
            keys.append(key_info)
        return keys
    except Exception as e:
        _log.error(f"Error listing API keys: {e}")
        return []
    finally:
        conn.close()


def delete_api_key(provider_name):
    """Delete an API key."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM api_keys WHERE provider_name = ?", (provider_name,))
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error deleting API key: {e}")
        return False
    finally:
        conn.close()


def set_active_provider(provider_name):
    """Set a provider as the active one (deactivates all others)."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE api_keys SET is_active = 0")
        cursor.execute("UPDATE api_keys SET is_active = 1 WHERE provider_name = ?", (provider_name,))
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error setting active provider: {e}")
        return False
    finally:
        conn.close()


def get_active_provider():
    """Get the currently active provider."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT provider_name, api_key_encrypted
            FROM api_keys
            WHERE is_active = 1
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            provider, encrypted_key = result
            if encrypted_key:
                api_key = decrypt_value(encrypted_key)
                return {"provider": provider, "api_key": api_key}
        return None
    except Exception as e:
        _log.error(f"Error getting active provider: {e}")
        return None
    finally:
        conn.close()


# ============================================================================
# Documents Management Functions
# ============================================================================


def save_document_metadata(filename, original_name, file_path, file_size, page_count=0):
    """
    Save document metadata. If a record with the same filename already exists,
    updates its size, page count and resets status to pending_index (re-upload).

    Returns:
        Document ID if successful, None otherwise
    """
    conn = _connect()
    try:
        cursor = conn.cursor()

        # Check for existing record
        cursor.execute("SELECT id FROM documents WHERE filename = ?", (filename,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE documents
                SET file_size = ?, page_count = ?, status = 'pending_index',
                    updated_at = CURRENT_TIMESTAMP
                WHERE filename = ?
            """,
                (file_size, page_count, filename),
            )
            doc_id = existing[0]
        else:
            cursor.execute("SELECT MAX(display_order) FROM documents")
            max_order = cursor.fetchone()[0] or 0
            cursor.execute(
                """
                INSERT INTO documents
                (filename, original_name, file_path, file_size, page_count, display_order, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending_index')
            """,
                (filename, original_name, file_path, file_size, page_count, max_order + 1),
            )
            doc_id = cursor.lastrowid

        conn.commit()
        return doc_id
    except Exception as e:
        _log.error(f"Error saving document metadata: {e}")
        return None
    finally:
        conn.close()


def get_all_documents(active_only=False):
    """Get all documents with metadata."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, filename, original_name, file_path, file_size,
                   page_count, display_order, is_active, status, created_at, updated_at
            FROM documents
        """
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY display_order"
        cursor.execute(query)
        results = cursor.fetchall()
        return [
            {
                "id": row[0],
                "filename": row[1],
                "original_name": row[2],
                "file_path": row[3],
                "file_size": row[4],
                "page_count": row[5],
                "display_order": row[6],
                "is_active": bool(row[7]),
                "status": row[8],
                "created_at": row[9],
                "updated_at": row[10],
            }
            for row in results
        ]
    except Exception as e:
        _log.error(f"Error getting documents: {e}")
        return []
    finally:
        conn.close()


def get_document_by_id(doc_id):
    """Get a single document by ID."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, original_name, file_path, file_size,
                   page_count, display_order, is_active, status
            FROM documents WHERE id = ?
        """,
            (doc_id,),
        )
        result = cursor.fetchone()
        if result:
            return {
                "id": result[0],
                "filename": result[1],
                "original_name": result[2],
                "file_path": result[3],
                "file_size": result[4],
                "page_count": result[5],
                "display_order": result[6],
                "is_active": bool(result[7]),
                "status": result[8],
            }
        return None
    except Exception as e:
        _log.error(f"Error getting document: {e}")
        return None
    finally:
        conn.close()


def update_document(doc_id, **kwargs):
    """Update document fields."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        valid_fields = ["filename", "original_name", "is_active", "status", "display_order", "page_count"]
        updates = []
        values = []
        for field, value in kwargs.items():
            if field in valid_fields:
                updates.append(f"{field} = ?")
                values.append(value)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(doc_id)
        cursor.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", values)  # nosec B608
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error updating document: {e}")
        return False
    finally:
        conn.close()


def delete_document(doc_id):
    """Delete a document from database."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error deleting document: {e}")
        return False
    finally:
        conn.close()


def reorder_documents(document_ids):
    """Reorder documents by providing ordered list of IDs."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        for index, doc_id in enumerate(document_ids):
            cursor.execute(
                "UPDATE documents SET display_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (index, doc_id)
            )
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error reordering documents: {e}")
        return False
    finally:
        conn.close()


# ============================================================================
# System Settings Functions
# ============================================================================


def get_setting(key, default=None):
    """Get a system setting value."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result[0] if result else default
    except Exception as e:
        _log.error(f"Error getting setting: {e}")
        return default
    finally:
        conn.close()


def set_setting(key, value):
    """Set a system setting value."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM settings WHERE key = ?", (key,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?", (value, key))
        else:
            cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error setting value: {e}")
        return False
    finally:
        conn.close()


# ============================================================================
# Audit Logging Functions
# ============================================================================


def log_admin_action(user_id, action_type, action_details=None, ip_address=None):
    """Log an admin action for audit trail."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (user_id, action_type, action_details, ip_address)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, action_type, action_details, ip_address),
        )
        conn.commit()
        return True
    except Exception as e:
        _log.error(f"Error logging action: {e}")
        return False
    finally:
        conn.close()
