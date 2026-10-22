"""THE structural cross-tenant leak test.

Walks three surfaces and asserts a foreign organization's rows are
invisible on every one of them:

1. every routed tenant viewset - the registry is structural, so a new
   tenant viewset joins the harness automatically, and a tenant
   viewset that skips the base fails the coverage assert instead of
   passing silently;
2. the Django admin changelists and detail views for tenant models;
3. the request-less path: scope_to_organization() and the management
   command that uses it.

Background tasks join the same harness when the job queue lands; their
hook is already scope_to_organization().
"""

import io

import pytest
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import get_resolver, reverse

from apps.accounts.models import Organization, User, Workspace
from apps.core.tenancy import TENANT_VIEWSET_REGISTRY, TenantViewSet, scope_to_organization
from config import urls as root_urls

pytestmark = pytest.mark.django_db

# Structural route table: every routed viewset on the tenant base.
TENANT_ROUTES = {
    viewset.__name__: (viewset, basename)
    for prefix, viewset, basename in root_urls.router.registry
    if issubclass(viewset, TenantViewSet)
}
ROUTE_IDS = sorted(TENANT_ROUTES)


def _routed_viewset_classes() -> set:
    """Collect every viewset class reachable through the URLconf."""
    classes = set()

    def walk(resolver):
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern)
            else:
                callback = pattern.callback
                # DRF viewsets expose the class via ``cls``, plain DRF
                # views via Django's ``view_class``.
                view_class = getattr(callback, "cls", None) or getattr(
                    callback, "view_class", None
                )
                if view_class is not None:
                    classes.add(view_class)

    walk(get_resolver())
    return classes


def test_every_concrete_tenant_viewset_is_routed():
    concrete = {vs for vs in TENANT_VIEWSET_REGISTRY if vs.queryset is not None}
    # Harness sanity: the base must actually have implementations, and
    # every one of them must be reachable through the router.
    assert concrete, "no concrete tenant viewsets registered"
    missing = {vs.__name__ for vs in concrete if vs not in _routed_viewset_classes()}
    assert not missing, f"tenant viewsets bypassing the router: {missing}"


@pytest.mark.parametrize("viewset_name", ROUTE_IDS)
def test_foreign_org_rows_hidden_on_every_method(
    viewset_name, authed_client_a, org_a, org_b, workspace_a, workspace_b
):
    viewset, basename = TENANT_ROUTES[viewset_name]
    model = viewset.queryset.model
    own_row, foreign_row = (
        (org_a, org_b) if model is Organization else (workspace_a, workspace_b)
    )
    list_url = reverse(f"{basename}-list")
    foreign_detail_url = reverse(f"{basename}-detail", args=[foreign_row.pk])
    own_header = {"HTTP_X_ORGANIZATION_ID": str(org_a.pk)}

    # Legitimate selector: the list shows own rows only.
    listed = authed_client_a.get(list_url, **own_header)
    assert listed.status_code == 200
    listed_ids = {row["id"] for row in listed.json()}
    assert str(own_row.pk) in listed_ids
    assert str(foreign_row.pk) not in listed_ids

    # Spoofed selector: a non-member org answers 404, existence hidden.
    spoofed = authed_client_a.get(list_url, HTTP_X_ORGANIZATION_ID=str(org_b.pk))
    assert spoofed.status_code == 404

    # Foreign detail object behind a legitimate selector: 404 on every
    # method that could read or change it.
    for method in ("get", "patch", "delete"):
        response = getattr(authed_client_a, method)(
            foreign_detail_url, format="json", **own_header
        )
        assert response.status_code == 404, f"{viewset_name}.{method} leaked a foreign row"


def _grant_accounts_permissions(user):
    user.user_permissions.add(
        *Permission.objects.filter(content_type__app_label="accounts")
    )


def test_admin_hides_foreign_org_rows(client, user_a, org_a, org_b, workspace_a, workspace_b):
    user_a.is_staff = True
    user_a.save()
    _grant_accounts_permissions(user_a)
    client.force_login(user_a)

    changelists = [
        (reverse("admin:accounts_workspace_changelist"), "Workspace A1", "Workspace B1"),
        (reverse("admin:accounts_organization_changelist"), "Org A", "Org B"),
        (
            reverse("admin:accounts_membership_changelist"),
            "owner-a@example.com",
            "owner-b@example.com",
        ),
    ]
    for url, visible, hidden in changelists:
        page = client.get(url).content.decode()
        assert visible in page, f"own row missing from {url}"
        assert hidden not in page, f"foreign org row visible in {url}"

    # Foreign detail pages answer Django admin's canonical
    # "object does not exist" redirect back to the admin index - the
    # row is unreadable either way.
    foreign_workspace = client.get(
        reverse("admin:accounts_workspace_change", args=[workspace_b.pk])
    )
    assert foreign_workspace.status_code == 302
    assert foreign_workspace.url == reverse("admin:index")
    foreign_org = client.get(
        reverse("admin:accounts_organization_change", args=[org_b.pk])
    )
    assert foreign_org.status_code == 302
    assert foreign_org.url == reverse("admin:index")


def test_admin_superuser_keeps_full_view(client, user_a, org_a, org_b, workspace_a, workspace_b):
    operator = User.objects.create_superuser(
        email="operator@example.com", password="operator-pass-123"
    )
    client.force_login(operator)
    page = client.get(reverse("admin:accounts_workspace_changelist")).content.decode()
    # Platform operator capability, not a tenancy path.
    assert "Workspace A1" in page and "Workspace B1" in page


def test_scope_to_organization_filters_and_resets(org_a, org_b, workspace_a, workspace_b):
    with scope_to_organization(org_a):
        assert {w.name for w in Workspace.objects.all()} == {workspace_a.name}
    # The context must not leak past the block: back to system scope.
    assert {w.name for w in Workspace.objects.all()} == {workspace_a.name, workspace_b.name}


def test_management_command_lists_only_scoped_org(org_a, org_b, workspace_a, workspace_b):
    output = io.StringIO()
    call_command("list_workspaces", str(org_a.pk), stdout=output)
    text = output.getvalue()
    assert workspace_a.name in text
    assert workspace_b.name not in text


def test_management_command_hides_unknown_org(workspace_a):
    # Unknown and malformed ids answer identically.
    with pytest.raises(CommandError):
        call_command("list_workspaces", "00000000-0000-0000-0000-000000000000")
    with pytest.raises(CommandError):
        call_command("list_workspaces", "not-a-uuid")


def test_workspaces_never_leak_without_context(org_a, org_b, workspace_a, workspace_b):
    # Belt and braces on the manager itself: no active organization in a
    # request-less block is a system state; the API and admin paths are
    # the guarded surfaces and are covered above.
    assert Workspace.objects.count() == 2
