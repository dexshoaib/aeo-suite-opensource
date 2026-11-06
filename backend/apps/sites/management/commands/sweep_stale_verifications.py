"""Management command to sweep stale verified sites and enqueue background re-verification."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.sites.reverification import iter_stale_sites_for_sweep, reverify_site

logger = logging.getLogger("aeo.sites.sweep")

# Pinned Postgres advisory lock key. Arbitrary but fixed.
ADVISORY_LOCK_KEY = 745_201_441


class Command(BaseCommand):
    help = "Sweep stale verified sites and enqueue reverify_site background tasks."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Select stale sites without enqueueing verification tasks.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of sites to sweep in this run (capped by global limit).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        interval_days = getattr(settings, "SITE_REVERIFICATION_INTERVAL_DAYS", None)
        per_org_limit = getattr(settings, "SITE_REVERIFICATION_PER_ORG_LIMIT", None)
        max_per_sweep = getattr(settings, "SITE_REVERIFICATION_MAX_PER_SWEEP", None)

        if (
            not isinstance(interval_days, int)
            or isinstance(interval_days, bool)
            or interval_days <= 0
        ):
            raise CommandError("SITE_REVERIFICATION_INTERVAL_DAYS must be a positive integer.")
        if (
            not isinstance(per_org_limit, int)
            or isinstance(per_org_limit, bool)
            or per_org_limit <= 0
        ):
            raise CommandError("SITE_REVERIFICATION_PER_ORG_LIMIT must be a positive integer.")
        if (
            not isinstance(max_per_sweep, int)
            or isinstance(max_per_sweep, bool)
            or max_per_sweep <= 0
        ):
            raise CommandError("SITE_REVERIFICATION_MAX_PER_SWEEP must be a positive integer.")

        dry_run: bool = options["dry_run"]
        limit_opt = options.get("limit")

        if limit_opt is not None:
            if not isinstance(limit_opt, int) or isinstance(limit_opt, bool) or limit_opt <= 0:
                raise CommandError("--limit must be a positive integer.")
            total_limit = min(limit_opt, max_per_sweep)
        else:
            total_limit = max_per_sweep

        # Postgres advisory lock for overlap control
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
            acquired = bool(cursor.fetchone()[0])

        if not acquired:
            summary = f"enqueued=0 orgs=0 dry_run={dry_run} lock=busy"
            logger.warning(summary)
            self.stdout.write(summary)
            return

        try:
            cutoff = timezone.now() - datetime.timedelta(days=interval_days)
            stale_pairs = list(
                iter_stale_sites_for_sweep(
                    cutoff=cutoff,
                    per_org_limit=per_org_limit,
                    total_limit=total_limit,
                )
            )

            distinct_orgs: set[Any] = set()
            enqueued_count = 0

            for site_id, org_id in stale_pairs:
                distinct_orgs.add(org_id)
                if not dry_run:
                    reverify_site.enqueue(str(site_id), organization=str(org_id))
                    enqueued_count += 1

            if dry_run:
                enqueued_count = len(stale_pairs)

            summary = (
                f"enqueued={enqueued_count} orgs={len(distinct_orgs)} dry_run={dry_run} lock=held"
            )
            logger.info(summary)
            self.stdout.write(summary)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])
