# Deploy PC Checker Extreme on Render

This app can be hosted on [Render](https://render.com) for the **web UI**, **scan history**, **compare**, and **export** features.

**Important:** Full PC diagnostics (WMI, PowerShell, winget, SMART) require **Windows**. On Render (Linux), scans will not collect real hardware from your machine. Run locally for complete checks:

```powershell
python manage.py runserver
```

---

## Option A — Blueprint (recommended)

1. Push this repo to **GitHub** or **GitLab**.
2. In Render: **New** → **Blueprint**.
3. Connect the repository — Render reads `render.yaml`.
4. Set **OPENAI_API_KEY** (optional) in the web service **Environment** tab after deploy.
5. Deploy. Your URL will be like `https://pc-checker-extreme.onrender.com`.

The blueprint creates:

- **Web service** (Python 3.11, Gunicorn)
- **PostgreSQL** database (free tier)

---

## Option B — Manual web service

1. **New** → **Web Service** → connect repo.
2. Settings:
   - **Runtime:** Python 3
   - **Build command:** `./build.sh`
   - **Start command:** `gunicorn pc_checker_extreme.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Health check path:** `/api/health/`
3. **New** → **PostgreSQL** — copy **Internal Database URL**.
4. Add environment variables:

| Key | Value |
|-----|--------|
| `DATABASE_URL` | *(from Postgres dashboard)* |
| `DJANGO_SECRET_KEY` | *(generate — Render can auto-generate)* |
| `DJANGO_DEBUG` | `false` |
| `OPENAI_API_KEY` | *(your key, optional)* |
| `PYTHON_VERSION` | `3.11.9` |

5. Deploy.

---

## Environment variables

| Variable | Required | Notes |
|----------|----------|--------|
| `DATABASE_URL` | Yes (Render) | From Render Postgres |
| `DJANGO_SECRET_KEY` | Yes | Long random string |
| `DJANGO_DEBUG` | No | `false` in production |
| `OPENAI_API_KEY` | No | AI reports |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini` |
| `PCC_API_KEY` | No | Protect `/api/scan/` |

Render sets automatically: `RENDER`, `RENDER_EXTERNAL_HOSTNAME`, `RENDER_EXTERNAL_URL`, `PORT`.

---

## After deploy

- Open your `*.onrender.com` URL.
- Health check: `https://your-app.onrender.com/api/health/`
- First request on free tier may be slow (cold start).

---

## Local vs Render

| Feature | Windows (local) | Render (cloud) |
|---------|-----------------|----------------|
| Dashboard UI | Yes | Yes |
| Save/compare scans | Yes | Yes (Postgres) |
| WMI hardware scan | Yes | No |
| winget updates | Yes | No |
| SMART / PowerShell | Yes | No |

Use **Render** to share the app UI and stored reports; use **local Windows** to scan your actual PC.
