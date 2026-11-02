# MINDMATE AI — updated Streamlit project

A local-first personal assistant with email/Google authentication, a chat interface backed by Ollama, an encrypted document vault, and email reminders.

## Included updates

- PDF upload limit: **25 MB** in chatbot attachments and the encrypted vault.
- Other chat attachments remain limited to 5 MB; other vault file types remain limited to 10 MB.
- Streamlit server upload limit set to 25 MB in `.streamlit/config.toml`.
- Chat replies stream as they arrive from Ollama. The Stop generation control cancels the active stream.
- Reminders open from the dashboard feature card (not the app navigation sidebar).
- A persistent bottom-left account control is available on dashboard, chatbot, vault, and reminders; its drop-up menu contains Log out.
- Reminder worker uses database claims to reduce duplicate sends and releases a claim after a failed email attempt.
- Existing authentication, chat history, reminder database, and AES-GCM vault storage formats are retained.

## Before replacing your current project

1. Stop the Streamlit app and reminder worker.
2. Make a backup copy of your entire existing project, especially `data/`, `mindmate_users.db`, `.streamlit/secrets.toml`, and the existing `MINDMATE_VAULT_KEY`.
3. Copy the files from this package into your project folder. Do **not** overwrite your real `.streamlit/secrets.toml` with the example file.
4. Keep your existing databases and encrypted vault files in place. Do not delete or regenerate the vault key.

## Setup

Use Python 3.11 or newer (the reminder worker uses `tomllib`). From the project directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you have not configured secrets yet, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in your own values. For an existing installation, keep the existing secrets file and especially its vault key unchanged.

Ollama must be installed and running locally. Pull the models configured in your secrets file (defaults):

```powershell
ollama pull qwen2.5:1.5b
ollama pull moondream
```

## Run the application

Open two terminals in the project directory, activate `.venv` in both, then run:

**Terminal 1 — Streamlit app**

```powershell
streamlit run app.py
```

**Terminal 2 — reminder email worker**

```powershell
python reminder_worker.py
```

Keep the worker running for scheduled reminder emails. The reminders page itself remains available even if the worker is stopped, but email notifications will not be processed until it runs.

## Notes and limitations

- Google sign-in requires valid Google OAuth credentials and a matching redirect URI. Apple sign-in is currently a setup notice/placeholder; it is not an active OAuth integration.
- Chat history is stored in SQLite as plain text; the Document Vault encrypts file contents at rest. See the module docstrings for details.
- PDFs are text-extracted locally. Scanned/image-only PDFs still need OCR and may report that no readable text was found.
- The local Ollama model must be installed and running on the same computer for chatbot responses.
- This package does not contain your private databases, uploaded documents, encrypted vault files, or real credentials.
