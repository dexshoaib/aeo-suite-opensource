"""Base model classes for every AEO Suite app (apps/core).

Abstract bases only - no tables, no migrations. Concrete apps inherit from
TimeStampedModel, which already carries the UUID primary key.

UUID primary keys are deliberate (owner directive, 2026-10-19 "Encrypt"
verdict): sequential integer ids leak volume and ordering information and
make organization enumeration easier; UUIDs plus the 404-not-403 rule
(ADR-0004) are the defense. If this ever changes, it must happen before
migration 0001 (Task 4), never after - like AUTH_USER_MODEL, a primary key
choice is painful to retrofit.
"""

import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    """Abstract base: non-guessable UUID primary key on every model."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDPrimaryKeyModel):
    """Abstract base: UUID pk + created/updated timestamps (UTC via USE_TZ)."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{type(self).__name__} ({self.pk})"
