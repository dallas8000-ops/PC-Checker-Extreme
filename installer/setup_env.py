"""
setup_env.py - Run once during installation by Inno Setup.

Writes a .env file with a cryptographically random SECRET_KEY so the
installed app never uses the insecure dev fallback key.
Skips silently if .env already exists (reinstall / upgrade scenario).
"""
import secrets
from pathlib import Path

env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    env_path.write_text(
        f"SECRET_KEY={secrets.token_urlsafe(50)}\n",
        encoding="utf-8",
    )
