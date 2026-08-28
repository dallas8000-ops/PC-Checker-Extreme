"""
setup_env.py - Run once during installation by Inno Setup.

Writes a .env file with a cryptographically random DJANGO_SECRET_KEY so the
installed app never uses the insecure dev fallback key, and pins DJANGO_DEBUG
to false. Without this, settings.py's IS_HOSTED check is False on a customer's
local machine (no RENDER/RAILWAY env vars present), so DEBUG defaults to
"true" — verbose tracebacks (including OPENAI_API_KEY / PCC_API_KEY values)
would be shown to the end user on any error.
Skips silently if .env already exists (reinstall / upgrade scenario).
"""
import secrets
from pathlib import Path

env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    env_path.write_text(
        f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}\n"
        "DJANGO_DEBUG=false\n",
        encoding="utf-8",
    )
