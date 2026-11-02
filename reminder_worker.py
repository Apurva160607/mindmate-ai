
import os
import time
import logging
import smtplib

from email.message import EmailMessage

from reminders_store import (
    claim_due_reminders,
    release_reminder_claim,
    get_notification_email,
    schedule_next_occurrence,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

CHECK_INTERVAL = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# --------------------------------------------------
# LOAD SMTP SETTINGS
# --------------------------------------------------

import tomllib
from pathlib import Path


def get_setting(name, default=""):
    # Environment variables take priority.
    value = os.getenv(name)

    if value:
        return value

    # Read the existing Streamlit secrets file.
    secrets_path = (
        Path(__file__).resolve().parent
        / ".streamlit"
        / "secrets.toml"
    )

    if secrets_path.exists():
        try:
            with open(secrets_path, "rb") as file:
                secrets = tomllib.load(file)

            return str(secrets.get(name, default))

        except Exception:
            logging.exception("Could not read SMTP configuration.")

    return default


# --------------------------------------------------
# SEND EMAIL
# --------------------------------------------------

def send_reminder_email(reminder):

    user_key = reminder.get("user_key")

    recipient = get_notification_email(user_key)

    if not recipient:
        logging.warning(
            "No notification email found for reminder %s.",
            reminder["id"]
        )
        return False

    host = get_setting("MINDMATE_SMTP_HOST")
    username = get_setting("MINDMATE_SMTP_USER")
    password = get_setting("MINDMATE_SMTP_PASSWORD")
    sender = get_setting("MINDMATE_EMAIL_FROM", username)

    try:
        port = int(get_setting("MINDMATE_SMTP_PORT", "587"))
    except ValueError:
        logging.error("Invalid SMTP port configuration.")
        return False

    if not all([host, username, password, sender]):
        logging.error("SMTP settings are incomplete.")
        return False

    message = EmailMessage()

    message["Subject"] = (
        f"MINDMATE AI Reminder: {reminder['title']}"
    )

    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        f"""
Hello!

This is your MINDMATE AI reminder.

Reminder: {reminder['title']}

Notes: {reminder.get('notes') or 'No additional notes'}

Open MINDMATE AI to manage this reminder.

Take care!
MINDMATE AI
"""
    )

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:

            server.starttls()
            server.login(username, password)
            server.send_message(message)

        logging.info(
            "Reminder email sent for reminder ID %s.",
            reminder["id"]
        )

        return True

    except Exception:
        logging.exception(
            "Email delivery failed for reminder ID %s.",
            reminder["id"]
        )

        return False


# --------------------------------------------------
# PROCESS DUE REMINDERS
# --------------------------------------------------

def process_due_reminders():

    reminders = claim_due_reminders()

    if not reminders:
        logging.info("No reminders are due.")
        return

    for reminder in reminders:

        logging.info(
            "Processing reminder: %s",
            reminder["title"]
        )

        sent = send_reminder_email(reminder)

        if sent:
            schedule_next_occurrence(reminder)
        else:
            # Release the five-minute claim so a later poll can retry delivery.
            release_reminder_claim(reminder["id"])


# --------------------------------------------------
# BACKGROUND WORKER
# --------------------------------------------------

def run_worker():

    logging.info(
        "MINDMATE AI reminder worker started."
    )

    while True:

        try:
            process_due_reminders()

        except Exception:
            logging.exception(
                "Unexpected error in reminder worker."
            )

        time.sleep(CHECK_INTERVAL)


# --------------------------------------------------
# START
# --------------------------------------------------

if __name__ == "__main__":
    run_worker()
