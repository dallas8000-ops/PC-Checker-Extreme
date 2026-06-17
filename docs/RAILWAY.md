# PC Checker Extreme — Railway deployment

## Service setup

1. Railway project → service linked to **`dallas8000-ops/PC-Checker-Extreme`**.
2. **Settings → Build → Builder:** **Dockerfile** (not Railpack). Root directory: empty.
3. Custom start command: **empty** — `railway.toml` runs `scripts/docker-start.sh`.
4. Connect **Postgres** via `DATABASE_URL`.

## Variables

| Name | Value |
|------|--------|
| `DJANGO_SECRET_KEY` | long random string |
| `DJANGO_DEBUG` | `false` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |

Optional: `OPENAI_API_KEY`, `PCC_API_KEY`, `CSRF_TRUSTED_ORIGINS`.

Do **not** set `PORT`.

## Verify

`https://pc-checker-extreme-production.up.railway.app/api/health/` → `{"status":"ok","app":"PC Checker Extreme"}`

If logs show `python app.py`, switch Builder to **Dockerfile** and redeploy.
