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
]


@override_settings(ROOT_URLCONF="stripe.tests")
class PortalIDORTest(TestCase):
    def setUp(self):
        self.attacker = get_user_model().objects.create_user(
            username="attacker",
            password="x",
        )
        self.client = Client()
        self.client.force_login(self.attacker)

    @patch("stripe.views.stripe")
    @patch("stripe.db.get_stripe_customer_for_user", return_value=None)
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

    @patch("stripe.views.stripe")
    @patch("stripe.db.get_stripe_customer_for_user", return_value="cus_OWNER_ACCOUNT")
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

    @patch("stripe.views.stripe")
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