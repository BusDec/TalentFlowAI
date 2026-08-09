"""Notifications app — outbox + pluggable providers.

Public API: ``notify(channel, to, subject, body) -> (bool, str)``
"""

from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def notify(channel: str, to: str, subject: str, body: str) -> Tuple[bool, str]:
    """Send a notification via the configured provider.

    1. Creates an outbox row (status=queued).
    2. Calls the provider.
    3. Updates status to sent/failed with any error detail.
    4. Never raises — returns ``(success, detail_or_error)``.
    """
    from .models import NotificationOutbox
    from .providers import get_provider

    outbox = NotificationOutbox.objects.create(
        channel=channel,
        to=to,
        subject=subject,
        body=body,
        status="queued",
    )

    try:
        provider = get_provider()
        ok, detail = provider.send(channel, to, subject, body)
    except Exception as exc:
        ok, detail = False, str(exc)
        logger.exception("Notification provider error for %s -> %s", channel, to)

    outbox.status = "sent" if ok else "failed"
    outbox.error = "" if ok else detail
    outbox.save(update_fields=["status", "error"])

    return ok, detail
