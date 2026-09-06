import os
import stripe

api_key = os.environ.get("STRIPE_SECRET_KEY")
if api_key:
    stripe.api_key = api_key


def require_configured() -> None:
    """Fail a billing operation closed when its server-side secret is absent."""
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
