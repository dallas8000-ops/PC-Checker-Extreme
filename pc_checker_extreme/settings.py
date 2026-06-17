import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

IS_RENDER = os.environ.get("RENDER", "").lower() in ("1", "true", "yes")
IS_RAILWAY = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RAILWAY_PROJECT_ID")
    or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
)
IS_HOSTED = IS_RENDER or IS_RAILWAY


def _django_build_command_running():
    if len(sys.argv) < 2:
        return False
    return sys.argv[1] in {"collectstatic", "migrate", "check"}


_django_secret = os.environ.get("DJANGO_SECRET_KEY", "").strip() or os.environ.get("SECRET_KEY", "").strip()
if _django_secret:
    SECRET_KEY = _django_secret
elif not IS_HOSTED or _django_build_command_running():
    SECRET_KEY = "django-insecure-dev-only-change-in-production"
else:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=false (production).")

DEBUG = os.environ.get("DJANGO_DEBUG", "false" if IS_HOSTED else "true").lower() in (
    "1",
    "true",
    "yes",
)


def _https_origin(host: str) -> str:
    host = host.strip()
    if not host:
        return ""
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"https://{host.lstrip('.')}"


def _append_origin(origins: list[str], value: str) -> None:
    origin = _https_origin(value)
    if origin and origin not in origins:
        origins.append(origin)


_allowed_env = os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip() or os.environ.get("ALLOWED_HOSTS", "").strip()
if IS_HOSTED and not _allowed_env:
    # Hosted: allow all hosts so internal/custom-domain health checks don't fail with 400.
    ALLOWED_HOSTS = ["*"]
else:
    _allowed = (_allowed_env or "127.0.0.1,localhost").split(",")
    if IS_RENDER:
        _allowed.append(".onrender.com")
        render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
        if render_host and render_host not in _allowed:
            _allowed.append(render_host)
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
        if render_url:
            parsed = urlparse(render_url)
            if parsed.hostname:
                _allowed.append(parsed.hostname)
    if IS_RAILWAY:
        for host in (".railway.app", ".up.railway.app", "healthcheck.railway.app"):
            if host not in _allowed:
                _allowed.append(host)
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain and railway_domain not in _allowed:
            _allowed.append(railway_domain)
    ALLOWED_HOSTS = [h.strip() for h in _allowed if h.strip()]

CSRF_TRUSTED_ORIGINS = []
_trusted = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if _trusted:
    for item in _trusted.split(","):
        _append_origin(CSRF_TRUSTED_ORIGINS, item)

if IS_RENDER:
    _append_origin(CSRF_TRUSTED_ORIGINS, os.environ.get("RENDER_EXTERNAL_URL", ""))
    for item in os.environ.get("CUSTOM_DOMAINS", "").split(","):
        _append_origin(CSRF_TRUSTED_ORIGINS, item)

if IS_RAILWAY:
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain:
        _append_origin(CSRF_TRUSTED_ORIGINS, railway_domain)

for host in ALLOWED_HOSTS:
    if host in ("*", "localhost", "127.0.0.1") or host.startswith("."):
        continue
    _append_origin(CSRF_TRUSTED_ORIGINS, host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "diagnostics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pc_checker_extreme.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "pc_checker_extreme.wsgi.application"

if os.environ.get("DATABASE_URL"):
    import dj_database_url

    _database_url = os.environ["DATABASE_URL"]
    _db_kwargs = {"conn_max_age": 600, "conn_health_checks": True}
    if _database_url.startswith("postgres://"):
        _database_url = "postgresql://" + _database_url[len("postgres://") :]
    if "railway.internal" in _database_url:
        if "sslmode=" not in _database_url:
            _database_url += "&sslmode=disable" if "?" in _database_url else "?sslmode=disable"
        _db_kwargs["ssl_require"] = False
    elif "railway" in _database_url:
        if "sslmode=" not in _database_url:
            _database_url += "&sslmode=require" if "?" in _database_url else "?sslmode=require"
        _db_kwargs["ssl_require"] = not DEBUG
    else:
        _db_kwargs["ssl_require"] = False
    DATABASES = {"default": dj_database_url.parse(_database_url, **_db_kwargs)}
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].setdefault("connect_timeout", 10)
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Railway probes /api/health/ over plain HTTP inside the container.
    SECURE_SSL_REDIRECT = False if IS_RAILWAY else os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "true").lower() in (
        "1",
        "true",
        "yes",
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/app/"
LOGOUT_REDIRECT_URL = "/"

# AI diagnostics
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Optional REST API key (header X-API-Key or ?api_key=)
PCC_API_KEY = os.environ.get("PCC_API_KEY", "")
