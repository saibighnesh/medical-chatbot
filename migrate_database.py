#!/usr/bin/env python3
"""
Database Migration Script
Migrates existing documents and .env API keys to new schema
"""

import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv
from PyPDF2 import PdfReader

# Load environment variables
load_dotenv()

DB_PATH = "users.db"
DATA_DIR = "Data"


def migrate_documents():
    """Migrate existing PDF files to documents table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if documents already exist
    cursor.execute("SELECT COUNT(*) FROM documents")
    if cursor.fetchone()[0] > 0:
        print("Documents already migrated, skipping...")
        conn.close()
        return

    print("Migrating existing PDF documents...")

    if not os.path.exists(DATA_DIR):
        print(f"  ⚠️  {DATA_DIR}/ directory not found")
        conn.close()
        return

    pdf_files = list(Path(DATA_DIR).glob("*.pdf"))

    for idx, pdf_path in enumerate(sorted(pdf_files)):
        try:
            # Get file metadata
            file_size = pdf_path.stat().st_size
            filename = pdf_path.name

            # Count pages
            page_count = 0
            try:
                pdf_reader = PdfReader(str(pdf_path))
                page_count = len(pdf_reader.pages)
            except:
                print(f"  ⚠️  Could not read page count for {filename}")

            # Insert into documents table
            cursor.execute(
                """
                INSERT INTO documents
                (filename, original_name, file_path, file_size, page_count, display_order, is_active, status)
                VALUES (?, ?, ?, ?, ?, ?, 1, 'indexed')
            """,
                (filename, filename, str(pdf_path), file_size, page_count, idx),
            )

            print(f"  ✓ Migrated: {filename} ({page_count} pages, {file_size:,} bytes)")

        except Exception as e:
            print(f"  ✗ Error migrating {pdf_path.name}: {e}")

    conn.commit()
    conn.close()
    print(f"✓ Migrated {len(pdf_files)} documents")


def migrate_api_keys():
    """Migrate API key from .env to database (unencrypted for now)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if API keys already exist
    cursor.execute("SELECT COUNT(*) FROM api_keys")
    if cursor.fetchone()[0] > 0:
        print("API keys already migrated, skipping...")
        conn.close()
        return

    print("Migrating API keys from .env...")

    google_api_key = os.getenv("GOOGLE_API_KEY")

    if google_api_key and google_api_key != "your_google_api_key_here":
        # For now, store unencrypted (will be encrypted in Phase 2)
        cursor.execute(
            """
            INSERT INTO api_keys (provider_name, api_key_encrypted, is_active)
            VALUES (?, ?, 1)
        """,
            ("gemini", google_api_key),
        )
        print("  ✓ Migrated Gemini API key")
    else:
        print("  ⚠️  No valid GOOGLE_API_KEY found in .env")

    # Add placeholders for other providers
    cursor.execute(
        """
        INSERT INTO api_keys (provider_name, api_key_encrypted, is_active)
        VALUES (?, ?, 0)
    """,
        ("openai", ""),
    )

    cursor.execute(
        """
        INSERT INTO api_keys (provider_name, api_key_encrypted, is_active)
        VALUES (?, ?, 0)
    """,
        ("claude", ""),
    )

    conn.commit()
    conn.close()
    print("✓ API keys migration complete")


def set_first_user_as_admin():
    """Set the first user as admin if no admins exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if any admin exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    admin_count = cursor.fetchone()[0]

    if admin_count == 0:
        # Get first user
        cursor.execute("SELECT id, username FROM users ORDER BY id LIMIT 1")
        result = cursor.fetchone()

        if result:
            user_id, username = result
            cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
            conn.commit()
            print(f"✓ Set '{username}' as admin user")
        else:
            print("  ⚠️  No users found. Create a user first.")
    else:
        print(f"✓ {admin_count} admin user(s) already exist")

    conn.close()


def main():
    print("=" * 60)
    print("Database Migration Script")
    print("=" * 60)
    print()

    # Run migrations
    migrate_documents()
    print()
    migrate_api_keys()
    print()
    set_first_user_as_admin()
    print()

    print("=" * 60)
    print("Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
