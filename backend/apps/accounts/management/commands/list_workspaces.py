"""List the workspaces of one organization - the request-less pattern.

Every query below runs inside scope_to_organization(), so the
auto-scoping base manager filters rows without a request. Future
background jobs copy exactly this shape: resolve the organization,
activate it, do the work, let the context close. The structural leak
test runs this command to prove the request-less path stays
organization-scoped.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Organization, Workspace
from apps.core.tenancy import scope_to_organization


class Command(BaseCommand):
    help = "List the workspaces of one organization."

    def add_arguments(self, parser):
        parser.add_argument("organization_id", help="UUID of the organization.")

    def handle(self, *args, **options):
        try:
            organization = Organization.objects.get(pk=options["organization_id"])
        except (Organization.DoesNotExist, ValidationError, ValueError) as exc:
            # Unknown and malformed ids answer identically - the command
            # never reveals whether an organization id exists.
            raise CommandError("Organization not found.") from exc

        with scope_to_organization(organization):
            workspaces = list(Workspace.objects.all())

        for workspace in workspaces:
            self.stdout.write(f"{workspace.pk}  {workspace.name}")
        self.stdout.write(self.style.SUCCESS(f"{len(workspaces)} workspace(s)."))
