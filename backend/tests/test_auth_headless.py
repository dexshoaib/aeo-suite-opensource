"""allauth headless browser-client flow, end to end without any UI.

signup -> session -> authenticated tenant call, and login -> tenant
call: the cookie session issued by the auth endpoints is what
authorizes the API call, which is the exact transport the frontend
uses.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

SIGNUP = reverse("headless:browser:account:signup")
LOGIN = reverse("headless:browser:account:login")
SESSION = reverse("headless:browser:account:current_session")


def test_signup_sets_session_and_authenticates_tenant_call(api_client):
    # The headless JSON contract is {email, password}: the password
    # confirmation field is a UI concern and does not exist here.
    response = api_client.post(
        SIGNUP,
        {
            "email": "new-owner@example.com",
            "password": "s3cret-pass-phrase",
        },
        format="json",
    )
    assert response.status_code == 200

    session = api_client.get(SESSION)
    assert session.status_code == 200
    assert session.json()["data"]["user"]["email"] == "new-owner@example.com"

    # The fresh session cookie alone authorizes a tenant call.
    listed = api_client.get(reverse("organizations-list"))
    assert listed.status_code == 200
    assert listed.json() == []


def test_login_flow_reaches_a_tenant_endpoint(api_client, user_a, org_a):
    response = api_client.post(
        LOGIN,
        {"email": user_a.email, "password": "test-password-a"},
        format="json",
    )
    assert response.status_code == 200

    listed = api_client.get(
        reverse("organizations-list"), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
    )
    assert listed.status_code == 200
    assert [row["name"] for row in listed.json()] == [org_a.name]


def test_login_rejects_wrong_password(api_client, user_a):
    response = api_client.post(
        LOGIN,
        {"email": user_a.email, "password": "definitely-wrong"},
        format="json",
    )
    assert response.status_code == 400


def test_anonymous_session_reports_unauthenticated(api_client):
    response = api_client.get(SESSION)
    # allauth answers 401 for an anonymous session probe.
    assert response.status_code == 401
    assert response.json()["meta"]["is_authenticated"] is False
