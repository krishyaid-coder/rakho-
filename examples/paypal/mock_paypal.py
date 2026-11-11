"""Mock PayPal. Nothing leaves this process. No token, no network."""

from __future__ import annotations

from dataclasses import dataclass, field

from origin import OriginHit, OriginIndex, mask_email


@dataclass
class InvoiceResult:
    status: str  # CREATED | BLOCKED
    payee_mask: str
    amount: str
    memo: str = ""
    invoice_id: str | None = None
    reason: str | None = None
    origin: OriginHit | None = None


@dataclass
class MockPayPal:
    sent: list[InvoiceResult] = field(default_factory=list)
    blocked: list[InvoiceResult] = field(default_factory=list)
    _n: int = 0

    def create_invoice(
        self,
        payee: str,
        amount: str,
        memo: str,
        origin: OriginIndex,
    ) -> InvoiceResult:
        hit = origin.check(payee)
        if hit is not None:
            result = InvoiceResult(
                status="BLOCKED",
                payee_mask=hit.mask,
                amount=amount,
                memo=memo,
                reason="origin_hit",
                origin=hit,
            )
            self.blocked.append(result)
            return result
        self._n += 1
        result = InvoiceResult(
            status="CREATED",
            payee_mask=mask_email(payee),
            amount=amount,
            memo=memo,
            invoice_id=f"INV-{self._n}",
        )
        self.sent.append(result)
        return result
