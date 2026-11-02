
import sqlite3
import calendar

from pathlib import Path
from datetime import datetime, timezone, timedelta


# ==================================================
# 1. DATABASE CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "reminders.db"

REPEAT_RULES = ("none", "daily", "weekly", "monthly")


# ==================================================
# 2. DATABASE CONNECTION
# ==================================================

def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def now_utc():
    return datetime.now(timezone.utc)


# ==================================================
# 3. DATABASE INITIALIZATION
# ==================================================

def init_db():

    with connect_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL,
                title TEXT NOT NULL,
                notes TEXT DEFAULT '',
                due_at TEXT NOT NULL,
                repeat_rule TEXT NOT NULL DEFAULT 'none',
                recurrence_day INTEGER,
                completed INTEGER DEFAULT 0,
                notified INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_user_due
            ON reminders(user_key, due_at)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_email_map (
                user_key TEXT PRIMARY KEY,
                email TEXT NOT NULL
            )
        """)

        # Add processing lock to existing databases.
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(reminders)"
            ).fetchall()
        }

        if "claim_until" not in columns:
            conn.execute("""
                ALTER TABLE reminders
                ADD COLUMN claim_until TEXT
            """)

        conn.commit()


# ==================================================
# 4. DATE AND TIME HANDLING
# ==================================================

def normalize_datetime(value):

    if value.tzinfo is None:
        raise ValueError(
            "Reminder time must include a timezone."
        )

    return value.astimezone(timezone.utc).isoformat()


def next_occurrence(due_at, repeat_rule, anchor_day=None):

    current = datetime.fromisoformat(due_at)

    if repeat_rule == "daily":
        return (
            current + timedelta(days=1)
        ).isoformat()

    if repeat_rule == "weekly":
        return (
            current + timedelta(weeks=1)
        ).isoformat()

    if repeat_rule == "monthly":

        original_day = anchor_day or current.day

        year = current.year
        month = current.month + 1

        if month > 12:
            month = 1
            year += 1

        last_day = calendar.monthrange(
            year,
            month
        )[1]

        return current.replace(
            year=year,
            month=month,
            day=min(original_day, last_day)
        ).isoformat()

    return None


# ==================================================
# 5. CREATE REMINDER
# ==================================================

def create_reminder(
    user_key,
    title,
    notes,
    due_at,
    repeat_rule="none"
):

    if not user_key:
        raise ValueError(
            "A valid logged-in user is required."
        )

    title = title.strip()

    if not title:
        raise ValueError(
            "Reminder title cannot be empty."
        )

    if repeat_rule not in REPEAT_RULES:
        raise ValueError(
            "Invalid recurrence option."
        )

    due = normalize_datetime(due_at)

    recurrence_day = (
        datetime.fromisoformat(due).day
        if repeat_rule == "monthly"
        else None
    )

    with connect_db() as conn:

        cursor = conn.execute("""
            INSERT INTO reminders (
                user_key,
                title,
                notes,
                due_at,
                repeat_rule,
                recurrence_day,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_key,
            title,
            (notes or "").strip(),
            due,
            repeat_rule,
            recurrence_day,
            now_utc().isoformat()
        ))

        conn.commit()

        return cursor.lastrowid


# ==================================================
# 6. READ REMINDERS
# ==================================================

def list_reminders(user_key):

    with connect_db() as conn:

        rows = conn.execute("""
            SELECT *
            FROM reminders
            WHERE user_key = ?
            ORDER BY due_at ASC
        """, (user_key,)).fetchall()

    return [dict(row) for row in rows]


def get_reminder(user_key, reminder_id):

    with connect_db() as conn:

        row = conn.execute("""
            SELECT *
            FROM reminders
            WHERE id = ?
              AND user_key = ?
        """, (
            reminder_id,
            user_key
        )).fetchone()

    return dict(row) if row else None


# ==================================================
# 7. UPDATE REMINDER
# ==================================================

def update_reminder(
    user_key,
    reminder_id,
    title,
    notes,
    due_at,
    repeat_rule="none"
):

    title = title.strip()

    if not title:
        raise ValueError(
            "Reminder title cannot be empty."
        )

    if repeat_rule not in REPEAT_RULES:
        raise ValueError(
            "Invalid recurrence option."
        )

    due = normalize_datetime(due_at)

    recurrence_day = (
        datetime.fromisoformat(due).day
        if repeat_rule == "monthly"
        else None
    )

    with connect_db() as conn:

        cursor = conn.execute("""
            UPDATE reminders
            SET
                title = ?,
                notes = ?,
                due_at = ?,
                repeat_rule = ?,
                recurrence_day = ?,
                completed = 0,
                notified = 0,
                claim_until = NULL

            WHERE id = ?
              AND user_key = ?
        """, (
            title,
            (notes or "").strip(),
            due,
            repeat_rule,
            recurrence_day,
            reminder_id,
            user_key
        ))

        conn.commit()

        return cursor.rowcount > 0


# ==================================================
# 8. COMPLETE / REOPEN REMINDER
# ==================================================

def set_completed(
    user_key,
    reminder_id,
    completed=True
):

    with connect_db() as conn:

        cursor = conn.execute("""
            UPDATE reminders
            SET
                completed = ?,
                notified = 0,
                claim_until = NULL

            WHERE id = ?
              AND user_key = ?
        """, (
            int(completed),
            reminder_id,
            user_key
        ))

        conn.commit()

        return cursor.rowcount > 0


# ==================================================
# 9. DELETE REMINDER
# ==================================================

def delete_reminder(user_key, reminder_id):

    with connect_db() as conn:

        cursor = conn.execute("""
            DELETE FROM reminders
            WHERE id = ?
              AND user_key = ?
        """, (
            reminder_id,
            user_key
        ))

        conn.commit()

        return cursor.rowcount > 0


# ==================================================
# 10. FETCH DUE REMINDERS
# ==================================================

def get_due_reminders():

    with connect_db() as conn:

        rows = conn.execute("""
            SELECT *
            FROM reminders

            WHERE completed = 0
              AND notified = 0
              AND due_at <= ?
        """, (
            now_utc().isoformat(),
        )).fetchall()

    return [dict(row) for row in rows]


# ==================================================
# 11. CLAIM DUE REMINDERS
# ==================================================

def claim_due_reminders():

    now = now_utc()

    claim_until = (
        now + timedelta(minutes=5)
    ).isoformat()

    with connect_db() as conn:

        conn.execute("BEGIN IMMEDIATE")

        rows = conn.execute("""
            SELECT *
            FROM reminders

            WHERE completed = 0
              AND notified = 0
              AND due_at <= ?
              AND (
                  claim_until IS NULL
                  OR claim_until <= ?
              )
        """, (
            now.isoformat(),
            now.isoformat()
        )).fetchall()

        reminders = [dict(row) for row in rows]

        for reminder in reminders:

            conn.execute("""
                UPDATE reminders
                SET claim_until = ?
                WHERE id = ?
                  AND completed = 0
                  AND notified = 0
            """, (
                claim_until,
                reminder["id"]
            ))

        conn.commit()

    return reminders


# ==================================================
# 12. RELEASE REMINDER CLAIM
# ==================================================

def release_reminder_claim(reminder_id):

    with connect_db() as conn:

        conn.execute("""
            UPDATE reminders
            SET claim_until = NULL

            WHERE id = ?
              AND notified = 0
        """, (reminder_id,))

        conn.commit()


# ==================================================
# 13. MARK REMINDER AS NOTIFIED
# ==================================================

def mark_notified(reminder_id):

    with connect_db() as conn:

        conn.execute("""
            UPDATE reminders
            SET
                notified = 1,
                claim_until = NULL

            WHERE id = ?
        """, (reminder_id,))

        conn.commit()


# ==================================================
# 14. SCHEDULE NEXT RECURRENCE
# ==================================================

def schedule_next_occurrence(reminder):

    # One-time reminder
    if reminder["repeat_rule"] == "none":

        with connect_db() as conn:

            conn.execute("""
                UPDATE reminders
                SET
                    notified = 1,
                    claim_until = NULL

                WHERE id = ?
                  AND user_key = ?
            """, (
                reminder["id"],
                reminder["user_key"]
            ))

            conn.commit()

        return

    # Recurring reminder
    next_due = reminder["due_at"]

    while True:

        next_due = next_occurrence(
            next_due,
            reminder["repeat_rule"],
            reminder["recurrence_day"]
        )

        if datetime.fromisoformat(next_due) > now_utc():
            break

    with connect_db() as conn:

        conn.execute("""
            UPDATE reminders
            SET
                due_at = ?,
                notified = 0,
                claim_until = NULL

            WHERE id = ?
              AND user_key = ?
        """, (
            next_due,
            reminder["id"],
            reminder["user_key"]
        ))

        conn.commit()


# ==================================================
# 15. SAVE NOTIFICATION EMAIL
# ==================================================

def save_notification_email(user_key, email):

    if not user_key or not email or "@" not in email:
        return False

    with connect_db() as conn:

        conn.execute("""
            INSERT INTO reminder_email_map (
                user_key,
                email
            )
            VALUES (?, ?)

            ON CONFLICT(user_key)
            DO UPDATE SET
                email = excluded.email
        """, (
            user_key,
            email.strip().lower()
        ))

        conn.commit()

    return True


# ==================================================
# 16. GET NOTIFICATION EMAIL
# ==================================================

def get_notification_email(user_key):

    if not user_key:
        return None

    # Email/password accounts
    if user_key.startswith("email:"):
        return user_key[len("email:"):]

    # Google accounts
    with connect_db() as conn:

        row = conn.execute("""
            SELECT email
            FROM reminder_email_map
            WHERE user_key = ?
        """, (user_key,)).fetchone()

    return row["email"] if row else None


# ==================================================
# 17. INITIALIZE DATABASE
# ==================================================

init_db()
