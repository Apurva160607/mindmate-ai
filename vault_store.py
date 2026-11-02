"""vault_store.py - encrypted, per-user document storage for the Document Vault.

HOW THE PROTECTION WORKS
  * Every file is encrypted with AES-256-GCM before it touches the disk.
  * The keys come from ONE secret master key (MINDMATE_VAULT_KEY) that lives in
    .streamlit/secrets.toml, NOT in the data folder. From it, a separate key is
    derived for every single file (HKDF-SHA256 over the master key, the owner and the
    file id). A stolen data/ folder alone is therefore unreadable.
  * The owner and file id are also bound into each encryption ("associated data"), so an
    encrypted file copied to another record, or another user, fails to decrypt.
  * Every query filters on user_key, which the server sets at login, so one user can never
    list, read, rename, replace or delete another user's documents.
  * File names are never used as paths: files are stored as <random uuid>.enc.
  * Uploads are checked by their real contents, size and per-user quota.

REMAINING LIMITATIONS (be honest about these)
  * Whoever holds BOTH the master key and the data folder can read everything.
  * Lose the master key and every file is gone for good. Back it up somewhere safe.
  * Deleting a file removes it from disk but cannot guarantee secure erasure on an SSD.
  * Titles, categories, sizes and dates are stored as normal database text (not encrypted).
  * The vault is only as safe as the computer it runs on and the logins in front of it.
"""
import base64
import binascii
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import NamedTuple, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import attachments as att

CATEGORIES = ["Medical", "Bills & Finance", "Identity", "Education", "Work", "Other"]
DEFAULT_CATEGORY = "Other"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DOCS_PER_USER = 100
MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_TITLE = 60
MAGIC = b"MMV1"                      # format marker + version at the start of every encrypted file
_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_items (
    id TEXT PRIMARY KEY,
    user_key TEXT NOT NULL,
    title TEXT NOT NULL,
    original_name TEXT NOT NULL,
    ext TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other'
);
CREATE INDEX IF NOT EXISTS idx_vault_user ON vault_items (user_key, updated_at);
CREATE TABLE IF NOT EXISTS vault_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key TEXT NOT NULL,
    action TEXT NOT NULL,
    doc_id TEXT,
    detail TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_events_user ON vault_events (user_key, ts);
"""


class VaultError(Exception):
    """A vault problem with a message that is safe to show to the user."""


class VaultItem(NamedTuple):
    id: str
    title: str
    original_name: str
    ext: str
    size: int
    created_at: float
    updated_at: float
    category: str


_COLUMNS = "id, title, original_name, ext, size, created_at, updated_at, category"


# ------------------------------------------------------------------ settings
def _paths():
    base = Path(__file__).resolve().parent / "data"
    vault_dir = Path(os.getenv("MINDMATE_VAULT_DIR") or base / "vault_files")
    db_path = Path(os.getenv("MINDMATE_VAULT_DB") or base / "vault.db")
    return vault_dir, db_path


def _setting(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def _master_key() -> bytes:
    raw = _setting("MINDMATE_VAULT_KEY").strip()
    if not raw:
        raise VaultError("The vault key is not set up yet.")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError) as exc:
        raise VaultError("MINDMATE_VAULT_KEY is not valid. Create a new one with the command in the setup guide.") from exc
    if len(key) != 32:
        raise VaultError("MINDMATE_VAULT_KEY must be exactly 32 random bytes. Create a new one with the setup command.")
    return key


def key_problem() -> str:
    """Empty string when the vault key is usable, otherwise what to fix."""
    try:
        _master_key()
        return ""
    except VaultError as exc:
        return str(exc)


# ---------------------------------------------------------------- encryption
def _file_key(user_key: str, doc_id: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=doc_id.encode("ascii"),
                info=b"mindmate-vault-file-v1|" + user_key.encode("utf-8")).derive(_master_key())


def _aad(user_key: str, doc_id: str) -> bytes:
    return f"mindmate|{user_key}|{doc_id}".encode("utf-8")


def _encrypt(user_key: str, doc_id: str, data: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_file_key(user_key, doc_id)).encrypt(nonce, data, _aad(user_key, doc_id))


def _decrypt(user_key: str, doc_id: str, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 12 + 16:
        raise VaultError("This file was stored in an older format. Please upload it again.")
    nonce, ciphertext = blob[4:16], blob[16:]
    try:
        return AESGCM(_file_key(user_key, doc_id)).decrypt(nonce, ciphertext, _aad(user_key, doc_id))
    except InvalidTag as exc:
        raise VaultError("This document could not be unlocked. It may be damaged, or the vault key changed.") from exc


def _write_atomic(path: Path, blob: bytes) -> None:
    """Write next to the target under a random temporary name, then swap it in in one step."""
    temp = path.with_name(f".tmp-{uuid.uuid4().hex}")
    try:
        temp.write_bytes(blob)
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


# ------------------------------------------------------------------ database
def _connect() -> sqlite3.Connection:
    vault_dir, db_path = _paths()
    vault_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(vault_items)")}
    if "category" not in columns:                         # tables created before categories existed
        conn.execute("ALTER TABLE vault_items ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'")
        conn.commit()
    return conn


def _check_user(user_key) -> str:
    if not isinstance(user_key, str) or not user_key.strip():
        raise VaultError("You must be signed in to use the vault.")
    return user_key


def _check_id(doc_id) -> str:
    if not isinstance(doc_id, str) or not _ID_RE.match(doc_id):
        raise VaultError("Document not found.")
    return doc_id


def clean_title(title: str) -> str:
    title = re.sub(r"[\x00-\x1f\x7f]", " ", str(title or ""))
    return re.sub(r"\s+", " ", title).strip()[:MAX_TITLE].strip()


def normalize_category(category: str) -> str:
    return category if category in CATEGORIES else DEFAULT_CATEGORY


def _log(conn, user_key: str, action: str, doc_id: Optional[str], detail: str = "") -> None:
    conn.execute("INSERT INTO vault_events (user_key, action, doc_id, detail, ts) VALUES (?, ?, ?, ?, ?)",
                 (user_key, action, doc_id, detail[:120], time.time()))


def log_event(user_key: str, action: str, doc_id: str = None, detail: str = "") -> None:
    _check_user(user_key)
    with closing(_connect()) as conn, conn:
        _log(conn, user_key, action, doc_id, detail)


def list_events(user_key: str, limit: int = 10) -> list:
    _check_user(user_key)
    with closing(_connect()) as conn:
        return conn.execute(
            "SELECT action, detail, ts FROM vault_events WHERE user_key = ? ORDER BY id DESC LIMIT ?",
            (user_key, int(limit))).fetchall()


# ----------------------------------------------------------------- documents
def list_documents(user_key: str, category: str = None, query: str = None) -> list:
    _check_user(user_key)
    sql, params = f"SELECT {_COLUMNS} FROM vault_items WHERE user_key = ?", [user_key]
    if category and category != "All":
        sql += " AND category = ?"
        params.append(normalize_category(category))
    query = str(query or "").strip()[:100]
    if query:
        like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (title LIKE ? ESCAPE '\\' OR original_name LIKE ? ESCAPE '\\')"
        params += [like, like]
    sql += " ORDER BY updated_at DESC, id"
    with closing(_connect()) as conn:
        return [VaultItem(*row) for row in conn.execute(sql, params).fetchall()]


def get_document(user_key: str, doc_id: str) -> Optional[VaultItem]:
    _check_user(user_key)
    if not isinstance(doc_id, str) or not _ID_RE.match(doc_id):
        return None
    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM vault_items WHERE id = ? AND user_key = ?",
                           (doc_id, user_key)).fetchone()
    return VaultItem(*row) if row else None


def usage(user_key: str):
    """(number of documents, total bytes) for this user."""
    _check_user(user_key)
    with closing(_connect()) as conn:
        count, total = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM vault_items WHERE user_key = ?", (user_key,)).fetchone()
    return int(count), int(total)


def _validate(name: str, data: bytes):
    try:
        return att.validate_file(name, data, MAX_FILE_BYTES)
    except att.AttachmentError as exc:
        raise VaultError(str(exc)) from exc


def save_document(user_key: str, original_name: str, data: bytes, title: str = None,
                  category: str = DEFAULT_CATEGORY) -> str:
    """Validate, encrypt and store a new document. Returns its id."""
    _check_user(user_key)
    _master_key()
    clean_name, ext = _validate(original_name, data)
    count, total = usage(user_key)
    if count >= MAX_DOCS_PER_USER:
        raise VaultError(f"Your vault is full ({MAX_DOCS_PER_USER} documents). Delete something first.")
    if total + len(data) > MAX_TOTAL_BYTES:
        raise VaultError(f"This would go over your {MAX_TOTAL_BYTES // (1024 * 1024)} MB vault limit.")

    doc_id = str(uuid.uuid4())
    vault_dir, _ = _paths()
    vault_dir.mkdir(parents=True, exist_ok=True)
    path = vault_dir / f"{doc_id}.enc"
    _write_atomic(path, _encrypt(user_key, doc_id, data))
    now = time.time()
    try:
        with closing(_connect()) as conn, conn:
            conn.execute(
                "INSERT INTO vault_items (id, user_key, title, original_name, ext, size, created_at, updated_at, category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, user_key, clean_title(title) or clean_title(os.path.splitext(clean_name)[0]) or "Untitled",
                 clean_name, ext, len(data), now, now, normalize_category(category)))
            _log(conn, user_key, "upload", doc_id, clean_name)
    except Exception:
        path.unlink(missing_ok=True)                      # never leave an unlisted encrypted file behind
        raise
    return doc_id


def read_decrypted(user_key: str, doc_id: str) -> bytes:
    doc = get_document(user_key, doc_id)
    if doc is None:
        raise VaultError("Document not found.")
    vault_dir, _ = _paths()
    path = vault_dir / f"{doc.id}.enc"
    if not path.exists():
        raise VaultError("The encrypted file is missing from storage.")
    return _decrypt(user_key, doc.id, path.read_bytes())


def replace_document(user_key: str, doc_id: str, new_name: str, data: bytes) -> bool:
    """Update: swap in a new version of the file, keeping the same document id, title and category."""
    doc = get_document(user_key, doc_id)
    if doc is None:
        raise VaultError("Document not found.")
    _master_key()
    clean_name, ext = _validate(new_name, data)
    _, total = usage(user_key)
    if total - doc.size + len(data) > MAX_TOTAL_BYTES:
        raise VaultError(f"This would go over your {MAX_TOTAL_BYTES // (1024 * 1024)} MB vault limit.")
    vault_dir, _ = _paths()
    path = vault_dir / f"{doc.id}.enc"
    blob = _encrypt(user_key, doc.id, data)
    conn = _connect()
    try:
        conn.execute("UPDATE vault_items SET original_name = ?, ext = ?, size = ?, updated_at = ? "
                     "WHERE id = ? AND user_key = ?", (clean_name, ext, len(data), time.time(), doc.id, user_key))
        _log(conn, user_key, "replace", doc.id, clean_name)
        _write_atomic(path, blob)                         # swapped in only if the database change worked
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return True


def rename_document(user_key: str, doc_id: str, new_title: str, category: str = None) -> bool:
    _check_user(user_key)
    title = clean_title(new_title)
    if not title or not isinstance(doc_id, str) or not _ID_RE.match(doc_id):
        return False
    with closing(_connect()) as conn, conn:
        if category is None:
            cur = conn.execute("UPDATE vault_items SET title = ?, updated_at = ? WHERE id = ? AND user_key = ?",
                               (title, time.time(), doc_id, user_key))
        else:
            cur = conn.execute("UPDATE vault_items SET title = ?, category = ?, updated_at = ? "
                               "WHERE id = ? AND user_key = ?",
                               (title, normalize_category(category), time.time(), doc_id, user_key))
        if cur.rowcount == 1:
            _log(conn, user_key, "rename", doc_id, title)
        return cur.rowcount == 1


def delete_document(user_key: str, doc_id: str) -> bool:
    """Delete only if this user owns it. (The file is removed ONLY after the ownership check passes.)"""
    _check_user(user_key)
    if not isinstance(doc_id, str) or not _ID_RE.match(doc_id):
        return False
    with closing(_connect()) as conn, conn:
        cur = conn.execute("DELETE FROM vault_items WHERE id = ? AND user_key = ?", (doc_id, user_key))
        deleted = cur.rowcount == 1
        if deleted:
            _log(conn, user_key, "delete", doc_id)
    if deleted:
        vault_dir, _ = _paths()
        try:
            (vault_dir / f"{doc_id}.enc").unlink(missing_ok=True)
        except OSError:
            pass
    return deleted
