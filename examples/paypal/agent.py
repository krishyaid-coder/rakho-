"""Payments agent from the PayPal × Sluice hackathon, with Rakho as the notebook.

No LLM. No PayPal token. Run:

    python3 examples/paypal/agent.py
    python3 examples/paypal/agent.py --sluice
    python3 examples/paypal/agent.py --sluice --actor krishy --db paypal-krishy.db --no-forget

Story:
  1. Read a poisoned invoice. Rakho refuses to keep it.
  2. The origin index fingerprints the attacker payee.
  3. create_invoice(attacker) is blocked. PayPal never sees the call.
  4. Read a clean invoice. Rakho keeps it.
  5. Recall only returns the vendor. create_invoice(vendor) goes through.
  6. Forget Krishy. The notebook is empty, and you can prove it.

Sluice is optional. Default gate already catches the injection. --sluice
swaps in Sluice as the inspector (pip install sluice-taint).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from origin import OriginHit, OriginIndex, extract_emails, mask_email  # noqa: E402
from mock_paypal import InvoiceResult, MockPayPal  # noqa: E402

from rakho import Rakho  # noqa: E402
from rakho.gate import PolicyGate  # noqa: E402
from rakho.models import KeepResult  # noqa: E402

INVOICES = HERE / "invoices"
POISONED = INVOICES / "invoice_3.md"
CLEAN = INVOICES / "invoice_clean.md"
ATTACKER = "sb-i1yp853787723@business.example.com"
VENDOR = "sb-27qgc53787689@business.example.com"


@dataclass
class Invoice:
    path: Path
    title: str
    payee: str
    amount: str
    memo: str
    raw: str


def parse_invoice(path: Path) -> Invoice:
    raw = path.read_text(encoding="utf-8")
    title = path.stem
    payee = ""
    amount = ""
    memo = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
        elif stripped.lower().startswith("payee:"):
            payee = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("amount:"):
            amount = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("memo:"):
            memo = stripped.split(":", 1)[1].strip()
    emails = extract_emails(raw)
    if not payee and emails:
        payee = emails[0]
    return Invoice(path=path, title=title, payee=payee, amount=amount, memo=memo, raw=raw)


def _inspect_labels(gate: PolicyGate, content: str) -> list[str]:
    decision = gate.inspect(content, {"origin_tool": "read_file"})
    return list(decision.labels)


@dataclass
class ReadResult:
    invoice: Invoice
    keep: KeepResult
    origin: list[OriginHit]


class PaymentsAgent:
    """Reads invoices, keeps notes in Rakho, pays through mock PayPal."""

    def __init__(
        self,
        db: Rakho,
        *,
        actor_id: str = "krishy",
        origin: OriginIndex | None = None,
        paypal: MockPayPal | None = None,
    ) -> None:
        self.db = db
        self.actor_id = actor_id
        self.origin = origin or OriginIndex()
        self.paypal = paypal or MockPayPal()

    def read_invoice(self, path: Path) -> ReadResult:
        invoice = parse_invoice(path)
        tagged = self.origin.tag(
            invoice.raw,
            _inspect_labels(self.db.gate, invoice.raw),
            source=str(path.name),
        )
        keep = self.db.keep(
            invoice.raw,
            actor_id=self.actor_id,
            source=str(path.name),
            origin_tool="read_file",
            session_id="paypal-demo",
        )
        return ReadResult(invoice=invoice, keep=keep, origin=tagged)

    def pay(self, invoice: Invoice) -> InvoiceResult:
        result = self.paypal.create_invoice(
            invoice.payee,
            invoice.amount,
            invoice.memo,
            self.origin,
        )
        # Ledger in the notebook: status + mask, never the raw payee.
        self.db.keep(
            (
                f"PayPal create_invoice {result.status} "
                f"id={result.invoice_id or '-'} amount={invoice.amount} "
                f"payee={result.payee_mask} file={invoice.path.name} "
                f"reason={result.reason or 'ok'}"
            ),
            actor_id=self.actor_id,
            source=invoice.path.name,
            origin_tool="create_invoice",
            session_id="paypal-demo",
        )
        return result

    def recall(self, query: str) -> list[str]:
        return [m.content for m in self.db.recall(query, actor_id=self.actor_id, k=5)]


def open_notebook(path: str | Path, *, sluice: bool) -> Rakho:
    return Rakho(path, gate="sluice" if sluice else "default")


def run_story(
    db: Rakho,
    *,
    actor_id: str = "krishy",
    forget: bool = True,
) -> dict[str, object]:
    agent = PaymentsAgent(db, actor_id=actor_id)

    poisoned = agent.read_invoice(POISONED)
    attacker_pay = agent.pay(poisoned.invoice)

    clean = agent.read_invoice(CLEAN)
    notes = agent.recall("consulting invoice")
    vendor_pay = agent.pay(clean.invoice)

    # Not a blocklist: same attacker, fresh session, never read the poison.
    unrelated = PaymentsAgent(db, actor_id=actor_id, origin=OriginIndex(), paypal=MockPayPal())
    attacker_unrelated = unrelated.pay(poisoned.invoice)

    leftover = db.audit(actor_id=actor_id)
    forgotten = 0
    if forget:
        result = db.forget(actor_id=actor_id)
        forgotten = result.deleted
        leftover = db.audit(actor_id=actor_id)

    return {
        "gate": type(db.gate).__name__,
        "poisoned_keep": poisoned.keep.action,
        "poisoned_reason": poisoned.keep.refused.reason if poisoned.keep.refused else "",
        "attacker_tagged": [h.mask for h in poisoned.origin],
        "attacker_paypal": attacker_pay.status,
        "clean_keep": clean.keep.action,
        "notes": notes,
        "vendor_paypal": vendor_pay.status,
        "vendor_invoice_id": vendor_pay.invoice_id,
        "attacker_without_read": attacker_unrelated.status,
        "memories_left": len(leftover.memories),
        "refusals_left": len(leftover.refusals),
        "stored": [m.content for m in leftover.memories],
        "refused": [(r.reason, r.preview) for r in leftover.refusals],
        "forgot": forgotten,
    }


def _print_story(story: dict[str, object], *, sluice: bool) -> None:
    hint = (
        "on  (Sluice inspects keep)"
        if sluice
        else "off  ·  enable: python3 examples/paypal/agent.py --sluice"
    )
    print("rakho  ·  payments agent  ·  PayPal mock, nothing leaves this process")
    print(f"gate:   {story['gate']}")
    print(f"sluice: {hint}")
    print()

    print("── 1. read poisoned invoice ──")
    print(f"file:   {POISONED.name}")
    print(f"payee:  {mask_email(ATTACKER)}")
    print(f"keep:   {story['poisoned_keep']}  ({story['poisoned_reason'] or 'stored'})")
    tagged = story["attacker_tagged"] or ["(none)"]
    print(f"origin: tagged  {', '.join(tagged)}")
    print()

    print("── 2. create_invoice that payee ──")
    print(f"PayPal: {story['attacker_paypal']}  (payee came from poisoned content)")
    print()

    print("── 3. read clean invoice ──")
    print(f"file:   {CLEAN.name}")
    print(f"payee:  {mask_email(VENDOR)}")
    print(f"keep:   {story['clean_keep']}")
    print()

    print("── 4. recall consulting invoice ──")
    notes = story["notes"] or ["(nothing)"]
    for note in notes:
        one = re.sub(r"\s+", " ", str(note)).strip()
        if len(one) > 88:
            one = one[:87] + "…"
        print(f"note:   {one}")
    print()

    print("── 5. create_invoice vendor ──")
    print(f"PayPal: {story['vendor_paypal']}  {story['vendor_invoice_id']}")
    print()

    print("── 6. same attacker, never read the poison ──")
    print(f"PayPal: {story['attacker_without_read']}  (not a blocklist)")
    print()

    if story["forgot"]:
        print("── 7. forget krishy ──")
        print(f"forgot {story['forgot']} rows  stored {story['memories_left']}  refused {story['refusals_left']}")
        return

    print("── 7. notebook left open (no forget) ──")
    print(f"stored {story['memories_left']}  refused {story['refusals_left']}")
    for note in story["stored"] or []:
        one = re.sub(r"\s+", " ", str(note)).strip()
        if len(one) > 96:
            one = one[:95] + "…"
        print(f"  keep  {one}")
    for reason, preview in story["refused"] or []:
        print(f"  skip  {reason}  {preview}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PayPal invoice agent that uses Rakho as memory.")
    parser.add_argument("--db", default="/tmp/rakho-paypal.db")
    parser.add_argument("--actor", default="krishy")
    parser.add_argument(
        "--sluice",
        action="store_true",
        help="inspect keep with Sluice (pip install sluice-taint). off by default.",
    )
    parser.add_argument(
        "--no-forget",
        action="store_true",
        help="leave Krishy's notebook on disk so you can dekho / sqlite3 it",
    )
    args = parser.parse_args(argv)

    try:
        db = open_notebook(args.db, sluice=args.sluice)
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        story = run_story(db, actor_id=args.actor, forget=not args.no_forget)
    finally:
        db.close()
    _print_story(story, sluice=args.sluice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
