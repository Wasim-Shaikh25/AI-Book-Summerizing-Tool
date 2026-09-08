"""User and platform storage repositories."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.modules.storage.knowledge_store import KnowledgeStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class UserRecord:
    user_id: str
    email: str
    display_name: str
    provider: str
    provider_user_id: str
    avatar_url: str | None = None


@dataclass
class ConversationRecord:
    conversation_id: str
    user_id: str
    book_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass
class MessageRecord:
    message_id: str
    conversation_id: str
    role: str
    content: str
    export_id: str | None
    metadata: dict[str, Any]
    created_at: str


@dataclass
class ExportRecord:
    export_id: str
    user_id: str
    file_path: str
    file_name: str
    created_at: str


class PlatformStore:
    """Extends knowledge DB with user/chat tables."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from src import config

            db_path = getattr(config, "KNOWLEDGE_DB_PATH", "output/knowledge_base.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        KnowledgeStore(db_path)
        self._init_platform_tables()

    def _init_platform_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                display_name TEXT,
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                avatar_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider
                ON users (provider, provider_user_id);

            CREATE TABLE IF NOT EXISTS user_books (
                user_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                file_path TEXT,
                log_dir TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, book_id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations (user_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                export_id TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages (conversation_id, created_at);

            CREATE TABLE IF NOT EXISTS exports (
                export_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        conn.close()

    def connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)


class UserRepository:
    def __init__(self, store: PlatformStore | None = None) -> None:
        self.store = store or PlatformStore()

    def upsert_oauth_user(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str,
        display_name: str,
        avatar_url: str | None,
    ) -> UserRecord:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, email, display_name, provider, provider_user_id, avatar_url "
            "FROM users WHERE provider = ? AND provider_user_id = ?",
            (provider, provider_user_id),
        )
        row = cur.fetchone()
        if row:
            user_id = row[0]
            cur.execute(
                "UPDATE users SET email = ?, display_name = ?, avatar_url = ? WHERE user_id = ?",
                (email, display_name, avatar_url, user_id),
            )
        else:
            user_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO users (user_id, email, display_name, provider, provider_user_id, avatar_url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, email, display_name, provider, provider_user_id, avatar_url),
            )
        conn.commit()
        conn.close()
        return UserRecord(user_id, email, display_name, provider, provider_user_id, avatar_url)

    def get_by_id(self, user_id: str) -> UserRecord | None:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, email, display_name, provider, provider_user_id, avatar_url "
            "FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return UserRecord(*row)


class UserBookRepository:
    def __init__(self, store: PlatformStore | None = None) -> None:
        self.store = store or PlatformStore()

    def link(self, user_id: str, book_id: str, file_path: str, log_dir: str | None) -> None:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO user_books (user_id, book_id, file_path, log_dir) VALUES (?, ?, ?, ?)",
            (user_id, book_id, file_path, log_dir),
        )
        conn.commit()
        conn.close()

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ub.book_id, ub.file_path, ub.log_dir, b.title, b.total_pages, b.processed_at
            FROM user_books ub
            JOIN books b ON b.book_id = ub.book_id
            WHERE ub.user_id = ?
            ORDER BY b.processed_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "book_id": r[0],
                "file_path": r[1],
                "log_dir": r[2],
                "title": r[3],
                "total_pages": r[4],
                "processed_at": r[5],
            }
            for r in rows
        ]

    def get(self, user_id: str, book_id: str) -> dict[str, Any] | None:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT book_id, file_path, log_dir FROM user_books WHERE user_id = ? AND book_id = ?",
            (user_id, book_id),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {"book_id": row[0], "file_path": row[1], "log_dir": row[2]}


class ConversationRepository:
    def __init__(self, store: PlatformStore | None = None) -> None:
        self.store = store or PlatformStore()

    def create(self, user_id: str, book_id: str, title: str = "New chat") -> ConversationRecord:
        conv_id = str(uuid.uuid4())
        now = _now_iso()
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversations (conversation_id, user_id, book_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, user_id, book_id, title, now, now),
        )
        conn.commit()
        conn.close()
        return ConversationRecord(conv_id, user_id, book_id, title, now, now)

    def list_for_user(self, user_id: str) -> list[ConversationRecord]:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT conversation_id, user_id, book_id, title, created_at, updated_at "
            "FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [ConversationRecord(*r) for r in rows]

    def get(self, conversation_id: str, user_id: str) -> ConversationRecord | None:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT conversation_id, user_id, book_id, title, created_at, updated_at "
            "FROM conversations WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return ConversationRecord(*row)

    def touch(self, conversation_id: str, title: str | None = None) -> None:
        conn = self.store.connection()
        cur = conn.cursor()
        if title:
            cur.execute(
                "UPDATE conversations SET updated_at = ?, title = ? WHERE conversation_id = ?",
                (_now_iso(), title, conversation_id),
            )
        else:
            cur.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (_now_iso(), conversation_id),
            )
        conn.commit()
        conn.close()


class MessageRepository:
    def __init__(self, store: PlatformStore | None = None) -> None:
        self.store = store or PlatformStore()

    def add(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        export_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        msg_id = str(uuid.uuid4())
        now = _now_iso()
        meta_json = json.dumps(metadata or {})
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages (message_id, conversation_id, role, content, export_id, metadata_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, conversation_id, role, content, export_id, meta_json, now),
        )
        conn.commit()
        conn.close()
        return MessageRecord(msg_id, conversation_id, role, content, export_id, metadata or {}, now)

    def list_for_conversation(self, conversation_id: str) -> list[MessageRecord]:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT message_id, conversation_id, role, content, export_id, metadata_json, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        )
        rows = cur.fetchall()
        conn.close()
        result = []
        for r in rows:
            meta = json.loads(r[5]) if r[5] else {}
            result.append(MessageRecord(r[0], r[1], r[2], r[3], r[4], meta, r[6]))
        return result

    def get_last_assistant(self, conversation_id: str) -> MessageRecord | None:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT message_id, conversation_id, role, content, export_id, metadata_json, created_at "
            "FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        meta = json.loads(row[5]) if row[5] else {}
        return MessageRecord(row[0], row[1], row[2], row[3], row[4], meta, row[6])


class ExportRepository:
    def __init__(self, store: PlatformStore | None = None) -> None:
        self.store = store or PlatformStore()

    def save(self, user_id: str, file_path: str, file_name: str) -> ExportRecord:
        export_id = str(uuid.uuid4())
        now = _now_iso()
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exports (export_id, user_id, file_path, file_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (export_id, user_id, file_path, file_name, now),
        )
        conn.commit()
        conn.close()
        return ExportRecord(export_id, user_id, file_path, file_name, now)

    def get(self, export_id: str, user_id: str) -> ExportRecord | None:
        conn = self.store.connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT export_id, user_id, file_path, file_name, created_at "
            "FROM exports WHERE export_id = ? AND user_id = ?",
            (export_id, user_id),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return ExportRecord(*row)
