# Domain & SSL Setup

Production URL: https://pc-checker-extreme-production.up.railway.app
Domain: pc-checker-extreme-production.up.railway.app
Framework: django

## SSL
SSL/TLS is automatic on Vercel, Railway, and Fly.io custom domains.

## Stripe Webhook (production)
Update webhook URL to: `https://pc-checker-extreme-production.up.railway.app/webhooks/stripe/`

## Verification
```bash
curl https://pc-checker-extreme-production.up.railway.app/health/
```
Run readiness from Stripe Installer after deploy.
