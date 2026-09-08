import inspect
import os
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

# stripe.client correctly fails closed outside tests when this is absent.
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_portal_regression")

from . import views

# Every test below runs against the REAL project URLconf (pc_checker_extreme.urls,
# the settings.py default -> billing.urls) instead of a hand-rolled parallel
# urlpatterns list. A previous version of this file defined its own urlpatterns
# with trailing slashes ("stripe/portal/", "stripe/pricing/", ...) that didn't
# match billing/urls.py's actual routes (registered WITHOUT trailing slashes:
# "portal", "pricing", ...) -- so these tests all passed while the real,
# deployed pricing/success/account/checkout/portal pages 404'd for every real
# visitor. Using the real URLconf is what makes these tests worth anything.


class PortalIDORTest(TestCase):
    def setUp(self):
        self.attacker = get_user_model().objects.create_user(
            username="attacker",
            password="x",
        )
        self.client = Client()
        self.client.force_login(self.attacker)

    @patch("billing.views.stripe")
    @patch("billing.db.get_stripe_customer_for_user", return_value=None)
    def test_spoofed_customer_id_is_ignored(self, mock_lookup, mock_stripe):
        response = self.client.post(
            "/stripe/portal",
            {"customerId": "cus_VICTIM_ACCOUNT"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {"error": "No Stripe customer linked to this account/session"},
        )
        mock_lookup.assert_called_once_with(self.attacker.pk)
        mock_stripe.billing_portal.Session.create.assert_not_called()

    @patch("billing.views.stripe")
    @patch("billing.db.get_stripe_customer_for_user", return_value="cus_OWNER_ACCOUNT")
    def test_authenticated_user_uses_only_its_server_linked_customer(
        self,
        mock_lookup,
        mock_stripe,
    ):
        mock_stripe.billing_portal.Session.create.return_value.url = "https://billing.stripe.test/session"

        response = self.client.post(
            "/stripe/portal",
            {"customerId": "cus_VICTIM_ACCOUNT"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://billing.stripe.test/session")
        mock_lookup.assert_called_once_with(self.attacker.pk)
        mock_stripe.billing_portal.Session.create.assert_called_once()
        self.assertEqual(
            mock_stripe.billing_portal.Session.create.call_args.kwargs["customer"],
            "cus_OWNER_ACCOUNT",
        )

    @patch("billing.views.stripe")
    def test_guest_uses_only_customer_from_its_session(self, mock_stripe):
        mock_stripe.billing_portal.Session.create.return_value.url = "https://billing.stripe.test/session"
        guest = Client()
        session = guest.session
        session["stripe_customer_id"] = "cus_GUEST_ACCOUNT"
        session.save()

        response = guest.post(
            "/stripe/portal",
            {"customerId": "cus_VICTIM_ACCOUNT"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            mock_stripe.billing_portal.Session.create.call_args.kwargs["customer"],
            "cus_GUEST_ACCOUNT",
        )


class RequireConfiguredGuardTest(TestCase):
    """Every billing action that talks to Stripe must fail closed when
    STRIPE_SECRET_KEY is absent. This guards against a future view (or an
    edit to an existing one) silently dropping the client.require_configured()
    call -- the exact regression that let this app hit Stripe with an unset key.
    """

    GUARDED_VIEWS = ("checkout", "portal", "webhook")

    def test_every_billing_action_calls_require_configured(self):
        source = inspect.getsource(views)
        for name in self.GUARDED_VIEWS:
            func_source = inspect.getsource(getattr(views, name))
            self.assertIn(
                "client.require_configured()",
                func_source,
                f"billing.views.{name} no longer guards on client.require_configured()",
            )
        self.assertGreaterEqual(source.count("client.require_configured()"), len(self.GUARDED_VIEWS))


class BillingPageRenderTest(TestCase):
    """Regression guard for the pricing page being static HTML disconnected
    from STRIPE_TIERS: this failed silently in production because nothing
    asserted that every configured tier actually renders on the page.
    """

    def test_pricing_renders_every_configured_tier(self):
        response = self.client.get("/stripe/pricing")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for tier in views.STRIPE_TIERS:
            self.assertIn(tier["price_id"], body)
            self.assertIn(tier["label"], body)

    def test_success_page_renders_for_guest(self):
        response = self.client.get("/stripe/success")
        self.assertEqual(response.status_code, 200)

    def test_account_page_renders_for_guest(self):
        response = self.client.get("/stripe/account")
        self.assertEqual(response.status_code, 200)


class RequireConfiguredInvocationTest(TestCase):
    @patch("billing.views.client.require_configured")
    def test_stripe_endpoints_require_server_key_configuration(self, mock_require_configured):
        guest = Client()
        guest.post("/stripe/checkout", {})
        guest.post("/stripe/portal", {})
        guest.post("/stripe/webhook", {})

        self.assertEqual(mock_require_configured.call_count, 3)


class CheckoutRedirectUrlTest(TestCase):
    """Regression test for two bugs found live in production on 2026-09-07:
    (1) success_url/cancel_url/return_url were hardcoded with a trailing slash
    ("/stripe/success/") that doesn't match billing/urls.py's actual routes
    ("success", no slash) -- every real checkout or portal-return sent the
    customer straight into a 404 instead of the app. (2) success_url never
    contained Stripe's "{CHECKOUT_SESSION_ID}" template token, so the redirect
    always carried an EMPTY session_id and success() could never link the
    paying customer's stripe_customer_id into their browser session.
    """

    # views.checkout()/portal() build the app's own origin from the APP_URL env
    # var (falling back to the production Railway domain), not from the
    # request -- so the expected origin here must match that same fallback,
    # not Django's test-client default ("http://testserver").
    EXPECTED_APP_URL = "https://pc-checker-extreme-production.up.railway.app"

    @patch("billing.views.stripe")
    def test_checkout_redirect_urls_match_real_routes_and_carry_session_id(self, mock_stripe):
        mock_stripe.checkout.Session.create.return_value.url = "https://checkout.stripe.test/session"

        response = self.client.post(
            "/stripe/checkout",
            {"priceId": "price_1UD6FoRxznXvj6jhZyk0Q2qp", "customerEmail": "buyer@example.com"},
        )

        self.assertEqual(response.status_code, 302)
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        self.assertEqual(
            kwargs["success_url"],
            f"{self.EXPECTED_APP_URL}{reverse('stripe-success')}?session_id={{CHECKOUT_SESSION_ID}}",
        )
        self.assertEqual(kwargs["cancel_url"], f"{self.EXPECTED_APP_URL}{reverse('stripe-pricing')}")

    @patch("billing.views.stripe")
    @patch("billing.db.get_stripe_customer_for_user", return_value="cus_OWNER_ACCOUNT")
    def test_portal_return_url_matches_real_account_route(self, mock_lookup, mock_stripe):
        mock_stripe.billing_portal.Session.create.return_value.url = "https://billing.stripe.test/session"
        user = get_user_model().objects.create_user(username="buyer", password="x")
        client = Client()
        client.force_login(user)

        client.post("/stripe/portal", {})

        kwargs = mock_stripe.billing_portal.Session.create.call_args.kwargs
        self.assertEqual(kwargs["return_url"], f"{self.EXPECTED_APP_URL}{reverse('stripe-account')}")


class StripeApiFailureTest(TestCase):
    """Regression test: before this fix, checkout()/portal() had no exception
    handling around the Stripe API call itself (only around the
    require_configured() guard) -- a Stripe-side failure (e.g. a price_id that
    doesn't exist under the deployed key's mode, or any transient API error)
    propagated as an unhandled exception straight to a Django 500 instead of a
    clean error response.
    """

    @patch("billing.views.stripe")
    def test_checkout_returns_clean_error_on_stripe_failure(self, mock_stripe):
        mock_stripe.error.StripeError = stripe.error.StripeError
        mock_stripe.checkout.Session.create.side_effect = stripe.error.StripeError("No such price")

        response = self.client.post(
            "/stripe/checkout",
            {"priceId": "price_1UD6FoRxznXvj6jhZyk0Q2qp", "customerEmail": "buyer@example.com"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())

    @patch("billing.views.stripe")
    @patch("billing.db.get_stripe_customer_for_user", return_value="cus_OWNER_ACCOUNT")
    def test_portal_returns_clean_error_on_stripe_failure(self, mock_lookup, mock_stripe):
        mock_stripe.error.StripeError = stripe.error.StripeError
        mock_stripe.billing_portal.Session.create.side_effect = stripe.error.StripeError("boom")
        user = get_user_model().objects.create_user(username="buyer2", password="x")
        client = Client()
        client.force_login(user)

        response = client.post("/stripe/portal", {})

        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())
