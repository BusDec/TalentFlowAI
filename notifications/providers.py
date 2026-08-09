"""Notification delivery providers.

Each provider implements ``send(channel, to, subject, body) -> (bool, str)``
returning ``(success, detail_or_error)``.  Providers MUST NOT raise — errors
are captured and returned as the second element.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Tuple


class NotificationProvider(ABC):
    """Interface every notification provider must implement."""

    @abstractmethod
    def send(self, channel: str, to: str, subject: str, body: str) -> Tuple[bool, str]:
        """Deliver a notification.

        Returns ``(True, "sent")`` on success or ``(False, "<error detail>")``
        on failure.  MUST NOT raise.
        """


class ConsoleProvider(NotificationProvider):
    """Default dev provider — prints to stdout and always succeeds."""

    def send(self, channel: str, to: str, subject: str, body: str) -> Tuple[bool, str]:
        print(f"[notify:{channel}] to={to} | {subject}: {body}")
        return True, "sent"


_PROVIDERS: dict[str, NotificationProvider] = {
    "console": ConsoleProvider(),
}


def get_provider() -> NotificationProvider:
    """Return the configured notification provider instance."""
    name = os.getenv("NOTIFY_PROVIDER", "console").strip().lower()
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise ValueError(f"Unknown notification provider: {name!r}")
    return provider
