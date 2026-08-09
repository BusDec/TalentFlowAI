"""Payment gateway adapters — §3.3 of Phase 3 design.

Provides a ``PaymentGateway`` ABC and two concrete implementations:

- ``MockPaymentGateway`` — always succeeds; used in dev/test and when
  ``PAYMENT_GATEWAY=mock`` (the default).
- ``RazorpayGateway`` — stub for production Razorpay integration; raises
  ``NotConfigured`` when API keys are absent.

Gateway selection is via the ``PAYMENT_GATEWAY`` environment variable
(default ``"mock"``).
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class NotConfigured(RuntimeError):
    """Raised when a payment gateway is selected but its credentials are missing."""


class PaymentGateway(ABC):
    """Interface every payment gateway must implement."""

    @abstractmethod
    def create_payment(self, amount: Decimal, reference: str) -> dict[str, Any]:
        """Initiate a payment and return ``{"id": ..., "url": ...}``.

        Parameters
        ----------
        amount:
            Charge amount in INR.
        reference:
            Application ID or internal reference for reconciliation.
        """

    @abstractmethod
    def verify(self, payload: dict[str, Any]) -> bool:
        """Verify a payment callback/webhook *payload*.

        Returns ``True`` when the payment is confirmed; ``False`` otherwise.
        """


class MockPaymentGateway(PaymentGateway):
    """Deterministic stub that always succeeds.

    Intended for development, testing, and CI environments.
    """

    def create_payment(self, amount: Decimal, reference: str) -> dict[str, Any]:
        payment_id = f"mock_{uuid.uuid4().hex[:12]}"
        return {
            "id": payment_id,
            "url": f"https://mock-gateway.example.com/pay/{payment_id}",
        }

    def verify(self, payload: dict[str, Any]) -> bool:
        return True


class RazorpayGateway(PaymentGateway):
    """Razorpay integration stub.

    Raises ``NotConfigured`` if ``RAZORPAY_KEY_ID`` or ``RAZORPAY_KEY_SECRET``
    are not set in the environment.  Actual API calls are deferred to a future
    iteration.
    """

    def __init__(self) -> None:
        self.key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        self.key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        if not self.key_id or not self.key_secret:
            raise NotConfigured(
                "Razorpay requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET "
                "environment variables."
            )

    def create_payment(self, amount: Decimal, reference: str) -> dict[str, Any]:
        # TODO: Wire up Razorpay Orders API.
        raise NotImplementedError("Razorpay integration not yet implemented.")

    def verify(self, payload: dict[str, Any]) -> bool:
        # TODO: Wire up Razorpay signature verification.
        raise NotImplementedError("Razorpay integration not yet implemented.")


def get_gateway() -> PaymentGateway:
    """Return the configured payment gateway instance.

    Reads ``PAYMENT_GATEWAY`` from the environment (default ``"mock"``).
    """
    name = os.environ.get("PAYMENT_GATEWAY", "mock").strip().lower()
    if name == "razorpay":
        return RazorpayGateway()
    if name == "mock":
        return MockPaymentGateway()
    raise ValueError(f"Unknown payment gateway: {name!r}")
