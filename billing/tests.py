import inspect
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import path

# stripe.client correctly fails closed outside tests when this is absent.
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_portal_regression")

from . import views


urlpatterns = [
    path("stripe/portal/", views.portal, name="stripe-portal"),
    path("stripe/pricing/", views.pricing, name="stripe-pricing"),
    path("stripe/checkout/", views.checkout, name="stripe-checkout"),
    path("stripe/success/", views.success, name="stripe-success"),
    path("stripe/account/", views.account, name="stripe-account"),
    path("stripe/webhook/", views.webhook, name="stripe-webhook"),
]


@override_settings(ROOT_URLCONF="billing.tests")
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
            "/stripe/portal/",
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
            "/stripe/portal/",
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
            "/stripe/portal/",
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
    call — the exact regression that let this app hit Stripe with an unset key.
    """

    GUARDED_VIEWS = ("checkout", "portal", "webhook")

    def test_every_billing_action_calls_require_configured(self):
        source = inspect.getsource(views)
        for name in self.GUARDED_VIEWS:
            func_source = inspect.getsource(getattr(views, name))
            self.assertIn(
                "client.require_configured()",
                func_source,
                f"stripe.views.{name} no longer guards on client.require_configured()",
            )
        self.assertGreaterEqual(source.count("client.require_configured()"), len(self.GUARDED_VIEWS))


@override_settings(ROOT_URLCONF="billing.tests")
class BillingPageRenderTest(TestCase):
    """Regression guard for the pricing page being static HTML disconnected
    from STRIPE_TIERS: this failed silently in production because nothing
    asserted that every configured tier actually renders on the page.
    """

    def test_pricing_renders_every_configured_tier(self):
        response = self.client.get("/stripe/pricing/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for tier in views.STRIPE_TIERS:
            self.assertIn(tier["price_id"], body)
            self.assertIn(tier["label"], body)

    def test_success_page_renders_for_guest(self):
        response = self.client.get("/stripe/success/")
        self.assertEqual(response.status_code, 200)

    def test_account_page_renders_for_guest(self):
        response = self.client.get("/stripe/account/")
        self.assertEqual(response.status_code, 200)


class RequireConfiguredInvocationTest(TestCase):
    @patch("billing.views.client.require_configured")
    def test_stripe_endpoints_require_server_key_configuration(self, mock_require_configured):
        guest = Client()
        guest.post("/stripe/checkout", {})
        guest.post("/stripe/portal", {})
        guest.post("/stripe/webhook", {})

        self.assertEqual(mock_require_configured.call_count, 3)
