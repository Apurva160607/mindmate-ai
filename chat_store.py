"""chat_store.py - local SQLite storage for chat history.

Security rule used everywhere in this file: every function receives `user_key`
(set by the server at login, never by the browser) and every SQL statement
filters on it. One user can therefore never read, rename, or delete another
user's chats, even if they guess a chat id.

Limitation: chats are stored as plain text in data/chats.db (not encrypted).
Only the Document Vault (Day 5) encrypts files at rest.
"""
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import NamedTuple, Optional

DEFAULT_TITLE = "New chat"
MAX_TITLE = 60
MAX_MESSAGE = 200_000   # safety cap only (about 30,000 words); the model has its own, smaller reading window

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chats_user ON chats (user_key, updated_at);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_id, id);
CREATE TABLE IF NOT EXISTS usage (
    user_key TEXT NOT NULL,
    day TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    messages INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_key, day)
);
"""


class Chat(NamedTuple):
    id: int
    title: str
    updated_at: float
    pinned: int


class Usage(NamedTuple):
    tokens: int
    messages: int


class Message(NamedTuple):
    role: str
    content: str


def _db_path() -> Path:
    override = os.getenv("MINDMATE_CHAT_DB")
    return Path(override) if override else Path(__file__).resolve().parent / "data" / "chats.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "context_tokens" not in columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 0"
    )

    if "pinned" not in columns:
        conn.execute(
            "ALTER TABLE chats ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
        )

    conn.commit()
    return conn


def _check_user(user_key) -> str:
    if not isinstance(user_key, str) or not user_key.strip():
        raise ValueError("A signed-in user is required.")
    return user_key


def clean_title(title: str) -> str:
    """Single line, no control characters, at most MAX_TITLE characters."""
    title = re.sub(r"[\x00-\x1f\x7f]", " ", str(title or ""))
    title = re.sub(r"\s+", " ", title).strip()
    return title[:MAX_TITLE].strip()


def create_chat(user_key: str, title: str = DEFAULT_TITLE) -> int:
    _check_user(user_key)
    now = time.time()
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO chats (user_key, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_key, clean_title(title) or DEFAULT_TITLE, now, now),
        )
        return cur.lastrowid


def list_chats(user_key: str) -> list:
    _check_user(user_key)
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT id, title, updated_at, pinned
            FROM chats
            WHERE user_key = ?
            ORDER BY pinned DESC, updated_at DESC, id DESC
            """,
            (user_key,),
        ).fetchall()
    return [Chat(*r) for r in rows]

def set_chat_pinned(user_key: str, chat_id: int, pinned: bool) -> bool:
    """Pin or unpin a chat belonging to the signed-in user."""
    _check_user(user_key)

    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            """
            UPDATE chats
            SET pinned = ?
            WHERE id = ? AND user_key = ?
            """,
            (1 if pinned else 0, chat_id, user_key),
        )
        return cur.rowcount == 1


def toggle_chat_pin(user_key: str, chat_id: int) -> bool:
    """Toggle pin status. Returns the new status, or False if not owned."""
    _check_user(user_key)

    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            """
            UPDATE chats
            SET pinned = CASE WHEN pinned = 1 THEN 0 ELSE 1 END
            WHERE id = ? AND user_key = ?
            """,
            (chat_id, user_key),
        )
        if cur.rowcount != 1:
            return False

        row = conn.execute(
            "SELECT pinned FROM chats WHERE id = ? AND user_key = ?",
            (chat_id, user_key),
        ).fetchone()

        return bool(row[0]) if row else False


def search_chats(user_key: str, query: str) -> list:
    """Chats whose title or any message contains `query` (this user's chats only)."""
    _check_user(user_key)
    query = str(query or "").strip()[:100]
    if not query:
        return list_chats(user_key)
    like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.updated_at, c.pinned FROM chats c WHERE c.user_key = ? AND ("
            " c.title LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM messages m WHERE m.chat_id = c.id"
            " AND m.content LIKE ? ESCAPE '\\')) ORDER BY c.pinned DESC, c.updated_at DESC, c.id DESC",
            (user_key, like, like),
        ).fetchall()
    return [Chat(*r) for r in rows]


def get_chat(user_key: str, chat_id: int) -> Optional[Chat]:
    _check_user(user_key)
    with closing(_connect()) as conn:
        row = conn.execute(
            """SELECT id, title, updated_at, pinned
               FROM chats
               WHERE id = ? AND user_key = ?""",
            (chat_id, user_key),
        ).fetchone()

    return Chat(*row) if row else None


def get_messages(user_key: str, chat_id: int) -> list:
    _check_user(user_key)
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT m.role, m.content FROM messages m JOIN chats c ON c.id = m.chat_id "
            "WHERE m.chat_id = ? AND c.user_key = ? ORDER BY m.id",
            (chat_id, user_key),
        ).fetchall()
    return [Message(*r) for r in rows]


def add_message(user_key: str, chat_id: int, role: str, content: str) -> bool:
    _check_user(user_key)
    if role not in ("user", "assistant") or not str(content).strip():
        return False
    now = time.time()
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) "
            "SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM chats WHERE id = ? AND user_key = ?)",
            (chat_id, role, str(content)[:MAX_MESSAGE], now, chat_id, user_key),
        )
        if cur.rowcount != 1:
            return False
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ? AND user_key = ?", (now, chat_id, user_key))
        return True


def rename_chat(user_key: str, chat_id: int, title: str) -> bool:
    _check_user(user_key)
    title = clean_title(title)
    if not title:
        return False
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE chats SET title = ? WHERE id = ? AND user_key = ?", (title, chat_id, user_key)
        )
        return cur.rowcount == 1


def delete_chat(user_key: str, chat_id: int) -> bool:
    _check_user(user_key)
    with closing(_connect()) as conn, conn:
        cur = conn.execute("DELETE FROM chats WHERE id = ? AND user_key = ?", (chat_id, user_key))
        return cur.rowcount == 1


def autotitle(user_key: str, chat_id: int, first_message: str) -> None:
    """Give a brand-new chat a title from its first message (never overwrites a renamed chat)."""
    title = clean_title(first_message)
    if not title:
        return
    _check_user(user_key)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE chats SET title = ? WHERE id = ? AND user_key = ? AND title = ?",
            (title[:40], chat_id, user_key, DEFAULT_TITLE),
        )


def _today() -> str:
    return time.strftime("%Y-%m-%d")        # local date: the daily counter resets at local midnight


def usage_today(user_key: str) -> Usage:
    """Tokens (prompt + reply) and number of answered messages for this user today."""
    _check_user(user_key)
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT prompt_tokens + completion_tokens, messages FROM usage WHERE user_key = ? AND day = ?",
            (user_key, _today()),
        ).fetchone()
    return Usage(*row) if row else Usage(0, 0)


def record_usage(user_key: str, chat_id: int, prompt_tokens: int, completion_tokens: int) -> None:
    """Add one answered message to today's counter and remember how full this chat's memory is."""
    _check_user(user_key)
    prompt_tokens, completion_tokens = max(0, int(prompt_tokens)), max(0, int(completion_tokens))
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO usage (user_key, day, prompt_tokens, completion_tokens, messages) VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(user_key, day) DO UPDATE SET prompt_tokens = prompt_tokens + excluded.prompt_tokens, "
            "completion_tokens = completion_tokens + excluded.completion_tokens, messages = messages + 1",
            (user_key, _today(), prompt_tokens, completion_tokens),
        )
        conn.execute(
            "UPDATE chats SET context_tokens = ? WHERE id = ? AND user_key = ?",
            (prompt_tokens + completion_tokens, chat_id, user_key),
        )


def get_context_tokens(user_key: str, chat_id: int) -> int:
    """How many tokens the model used for this chat's latest reply (0 if unknown)."""
    _check_user(user_key)
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT context_tokens FROM chats WHERE id = ? AND user_key = ?", (chat_id, user_key)
        ).fetchone()
    return int(row[0]) if row else 0
