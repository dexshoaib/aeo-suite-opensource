"""Role ladder for permission gates (SPEC-1.2 amendment 1/6).

The membership Role choices are owner/member today (agency roles land
later). The ladder names the target roles so gates are written once:
``member`` maps to editor level now, so a gate written for "editor or
above" activates automatically when viewer/editor roles land.
"""

ROLE_LEVELS: dict[str, int] = {
    "viewer": 1,
    "editor": 2,
    "admin": 3,
    "owner": 4,
}
# Today's operator role sits at editor level.
ROLE_LEVELS["member"] = ROLE_LEVELS["editor"]

EDITOR = "editor"


def role_at_least(role: str, minimum: str = EDITOR) -> bool:
    """Pure ladder comparison; unknown roles fail closed."""
    level = ROLE_LEVELS.get(role)
    return level is not None and level >= ROLE_LEVELS[minimum]


def user_has_org_role(user, organization, minimum: str = EDITOR) -> bool:
    """Server-side membership check (ADR-0004 rule 3) against the ladder."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if organization is None:
        return False
    from apps.accounts.models import Membership

    membership = Membership.objects.filter(user=user, organization=organization).first()
    return membership is not None and role_at_least(membership.role, minimum)
