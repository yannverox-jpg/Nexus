"""Revenue and payout tracking without storing payment credentials."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import sqlite3
import uuid

try:
    from .sqlite_storage import connect_sqlite
except ImportError:
    from sqlite_storage import connect_sqlite
from typing import Any


ACTIVE_PAYOUT_STATES = {
    "WAITING_PROVIDER_SETUP", "READY_FOR_MANUAL_REQUEST", "REQUESTED_EXTERNALLY",
    "PROCESSING", "REVIEW_REQUIRED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money_minor(value: Any) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Montant invalide") from exc
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValueError("Le montant doit être positif et limité à deux décimales")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _currency(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("La devise doit être un code de trois lettres, par exemple EUR")
    return value


def _assert_no_card_secrets(value: str) -> None:
    if re.search(r"(?i)\b(cvv|cvc|security code|code de sécurité)\b", value):
        raise ValueError("Les données CVV/CVC ne sont jamais acceptées")
    digits = re.sub(r"\D", "", value)
    if 13 <= len(digits) <= 19:
        raise ValueError("Un numéro de carte complet ne doit pas être saisi")


def _display_amount(minor: int) -> str:
    return f"{Decimal(minor) / 100:.2f}"


class PayoutLedger:
    """Track reported income, payout readiness, and externally confirmed outcomes.

    This ledger never initiates transfers and intentionally has no PAN/CVV fields.
    """

    def __init__(self, database_path: str):
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.database_path, timeout=30)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payout_destinations (
                    destination_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    destination_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    last4 TEXT,
                    currency TEXT NOT NULL,
                    setup_status TEXT NOT NULL,
                    setup_reference TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            destination_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(payout_destinations)")
            }
            if "setup_reference" not in destination_columns:
                conn.execute("ALTER TABLE payout_destinations ADD COLUMN setup_reference TEXT")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS platform_accounts (
                    account_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    account_reference TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    balance_minor INTEGER NOT NULL CHECK(balance_minor >= 0),
                    evidence_reference TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, account_reference, currency)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS revenue_entries (
                    entry_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    status TEXT NOT NULL,
                    evidence_reference TEXT,
                    earned_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payout_orders (
                    order_id TEXT PRIMARY KEY,
                    destination_id TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    status TEXT NOT NULL,
                    external_reference TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(destination_id) REFERENCES payout_destinations(destination_id)
                )
            """)

    def register_platform_account(
        self, *, platform: str, account_reference: str, currency: str,
        balance: Any, evidence_reference: str, observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Record an external platform account snapshot; Nexus never owns its funds."""
        platform = platform.strip()
        account_reference = account_reference.strip()
        evidence_reference = evidence_reference.strip()
        for value in (platform, account_reference, evidence_reference):
            _assert_no_card_secrets(value)
        if not platform or len(platform) > 100:
            raise ValueError("Le nom de la plateforme est obligatoire")
        if not account_reference or len(account_reference) > 200:
            raise ValueError("Une référence de compte externe est requise")
        if not evidence_reference or len(evidence_reference) > 200:
            raise ValueError("Une preuve externe vérifiable est requise")
        amount = Decimal(str(balance))
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError("Le solde doit être positif ou nul et limité à deux décimales")
        minor = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        currency = _currency(currency)
        now = _now()
        observed = observed_at or now
        account_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO platform_accounts
                (account_id,platform,account_reference,currency,balance_minor,evidence_reference,observed_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(platform,account_reference,currency) DO UPDATE SET
                    balance_minor=excluded.balance_minor,
                    evidence_reference=excluded.evidence_reference,
                    observed_at=excluded.observed_at,
                    updated_at=excluded.updated_at""",
                (account_id, platform, account_reference, currency, minor,
                 evidence_reference, observed, now, now),
            )
            row = conn.execute(
                "SELECT * FROM platform_accounts WHERE platform=? AND account_reference=? AND currency=?",
                (platform, account_reference, currency),
            ).fetchone()
        return self._platform_account_view(dict(row))

    @staticmethod
    def _platform_account_view(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result["balance"] = _display_amount(result.pop("balance_minor"))
        result["ownership"] = "EXTERNAL_PLATFORM_ACCOUNT"
        return result

    def list_platform_accounts(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM platform_accounts ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self._platform_account_view(dict(row)) for row in rows]

    def _list(self, table: str, limit: int = 200) -> list[dict[str, Any]]:
        allowed = {"payout_destinations", "platform_accounts", "revenue_entries", "payout_orders"}
        if table not in allowed:
            raise ValueError("Table inconnue")
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_destination(
        self, *, provider: str, destination_type: str, label: str,
        currency: str, last4: str | None = None,
    ) -> dict[str, Any]:
        provider, label = provider.strip(), label.strip()
        _assert_no_card_secrets(provider)
        _assert_no_card_secrets(label)
        destination_type = destination_type.strip().upper()
        if not provider or not label or len(provider) > 80 or len(label) > 100:
            raise ValueError("Le fournisseur et le libellé sont obligatoires")
        if destination_type != "CARD":
            raise ValueError("Seule la carte Visa prépayée externe est configurée comme destination de retrait")
        if destination_type == "CARD" and not re.fullmatch(r"\d{4}", last4 or ""):
            raise ValueError("Pour une carte, seuls les quatre derniers chiffres sont acceptés")
        if last4 is not None and not re.fullmatch(r"\d{4}", last4):
            raise ValueError("N’indiquer que les quatre derniers chiffres")
        destination = {
            "destination_id": str(uuid.uuid4()),
            "provider": provider,
            "destination_type": destination_type,
            "label": label,
            "last4": last4,
            "currency": _currency(currency),
            "setup_status": "PROVIDER_SETUP_REQUIRED",
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO payout_destinations "
                "(destination_id,provider,destination_type,label,last4,currency,setup_status,setup_reference,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (destination["destination_id"], destination["provider"],
                 destination["destination_type"], destination["label"],
                 destination["last4"], destination["currency"],
                 destination["setup_status"], None, destination["created_at"]),
            )
        return destination

    def add_revenue(
        self, *, source: str, category: str, amount: Any, currency: str,
        earned_at: str | None = None,
    ) -> dict[str, Any]:
        source, category = source.strip(), category.strip().lower()
        if not source or len(source) > 120:
            raise ValueError("La plateforme/source est obligatoire")
        if category not in {"microservices", "ecommerce", "sports", "trading", "other"}:
            raise ValueError("Catégorie inconnue")
        minor = _money_minor(amount)
        now = _now()
        entry = {
            "entry_id": str(uuid.uuid4()), "source": source, "category": category,
            "currency": _currency(currency), "amount_minor": minor,
            "status": "REPORTED", "evidence_reference": None,
            "earned_at": earned_at or now, "created_at": now, "updated_at": now,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO revenue_entries VALUES(?,?,?,?,?,?,?,?,?,?)",
                tuple(entry.values()),
            )
        return self._revenue_view(entry)

    def confirm_revenue(self, entry_id: str, evidence_reference: str) -> dict[str, Any]:
        reference = evidence_reference.strip()
        _assert_no_card_secrets(reference)
        if not reference or len(reference) > 200:
            raise ValueError("Une référence vérifiable de la plateforme est requise")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM revenue_entries WHERE entry_id=?", (entry_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Revenu introuvable")
            if row["status"] != "REPORTED":
                raise ValueError("Seul un revenu signalé peut être confirmé")
            conn.execute(
                "UPDATE revenue_entries SET status='PAYABLE', evidence_reference=?, updated_at=? WHERE entry_id=?",
                (reference, _now(), entry_id),
            )
            updated = conn.execute(
                "SELECT * FROM revenue_entries WHERE entry_id=?", (entry_id,)
            ).fetchone()
        return self._revenue_view(dict(updated))

    def confirm_destination(self, destination_id: str, confirmation_reference: str) -> dict[str, Any]:
        reference = confirmation_reference.strip()
        _assert_no_card_secrets(reference)
        if not reference or len(reference) > 200:
            raise ValueError("Une référence de configuration externe est requise")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM payout_destinations WHERE destination_id=?",
                (destination_id,),
            ).fetchone()
            if row is None:
                raise KeyError("Destination introuvable")
            conn.execute(
                "UPDATE payout_destinations SET setup_status='MANUALLY_CONFIRMED', setup_reference=? WHERE destination_id=?",
                (reference, destination_id),
            )
            updated = conn.execute(
                "SELECT * FROM payout_destinations WHERE destination_id=?",
                (destination_id,),
            ).fetchone()
        result = dict(updated)
        return result

    def create_payout_order(
        self, *, destination_id: str, amount: Any, currency: str,
    ) -> dict[str, Any]:
        currency = _currency(currency)
        minor = _money_minor(amount)
        now = _now()
        order_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            destination = conn.execute(
                "SELECT * FROM payout_destinations WHERE destination_id=?",
                (destination_id,),
            ).fetchone()
            if destination is None:
                raise KeyError("Destination introuvable")
            if destination["currency"] != currency:
                raise ValueError("La devise ne correspond pas à la destination")
            payable = conn.execute(
                "SELECT COALESCE(SUM(amount_minor), 0) FROM revenue_entries WHERE status='PAYABLE' AND currency=?",
                (currency,),
            ).fetchone()[0]
            reserved = conn.execute(
                "SELECT COALESCE(SUM(amount_minor), 0) FROM payout_orders WHERE currency=? AND status IN ({})".format(
                    ",".join("?" for _ in (ACTIVE_PAYOUT_STATES | {"PAID"}))
                ),
                (currency, *sorted(ACTIVE_PAYOUT_STATES | {"PAID"})),
            ).fetchone()[0]
            if minor > payable - reserved:
                raise ValueError(
                    f"Solde payable disponible : {_display_amount(max(0, payable - reserved))} {currency}"
                )
            status = (
                "READY_FOR_MANUAL_REQUEST"
                if destination["setup_status"] == "MANUALLY_CONFIRMED"
                else "WAITING_PROVIDER_SETUP"
            )
            conn.execute(
                "INSERT INTO payout_orders VALUES(?,?,?,?,?,?,?,?,?)",
                (order_id, destination_id, currency, minor, status, None,
                 "Nexus ne transmet pas de fonds; demande externe requise.", now, now),
            )
            row = conn.execute(
                "SELECT * FROM payout_orders WHERE order_id=?", (order_id,)
            ).fetchone()
        return self._payout_view(dict(row), dict(destination))

    def update_payout_order(
        self, order_id: str, *, status: str, external_reference: str,
    ) -> dict[str, Any]:
        status = status.strip().upper()
        if status not in {"REQUESTED_EXTERNALLY", "PROCESSING", "PAID", "FAILED", "REVIEW_REQUIRED", "CANCELLED"}:
            raise ValueError("Statut de versement invalide")
        reference = external_reference.strip()
        _assert_no_card_secrets(reference)
        if not reference or len(reference) > 200:
            raise ValueError("Une référence externe est requise pour le rapprochement")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT p.*, d.provider, d.label, d.destination_type, d.last4, d.setup_status "
                "FROM payout_orders p JOIN payout_destinations d USING(destination_id) WHERE order_id=?",
                (order_id,),
            ).fetchone()
            if row is None:
                raise KeyError("Ordre de versement introuvable")
            if row["status"] not in ACTIVE_PAYOUT_STATES:
                raise ValueError("Cet ordre n’est plus modifiable")
            conn.execute(
                "UPDATE payout_orders SET status=?, external_reference=?, updated_at=? WHERE order_id=?",
                (status, reference, _now(), order_id),
            )
            updated = conn.execute(
                "SELECT p.*, d.provider, d.label, d.destination_type, d.last4, d.setup_status "
                "FROM payout_orders p JOIN payout_destinations d USING(destination_id) WHERE order_id=?",
                (order_id,),
            ).fetchone()
        return self._payout_view(dict(updated))

    @staticmethod
    def _revenue_view(entry: dict[str, Any]) -> dict[str, Any]:
        result = dict(entry)
        result["amount"] = _display_amount(result.pop("amount_minor"))
        return result

    @staticmethod
    def _payout_view(order: dict[str, Any], destination: dict[str, Any] | None = None) -> dict[str, Any]:
        result = dict(order)
        result["amount"] = _display_amount(result.pop("amount_minor"))
        if destination:
            result["destination"] = {
                key: destination.get(key) for key in (
                    "destination_id", "provider", "destination_type", "label",
                    "last4", "currency", "setup_status", "setup_reference",
                )
            }
        return result

    def overview(self) -> dict[str, Any]:
        destinations = self._list("payout_destinations")
        revenues = [self._revenue_view(item) for item in self._list("revenue_entries")]
        orders = self._list("payout_orders")
        destination_map = {item["destination_id"]: item for item in destinations}
        payouts = [
            self._payout_view(item, destination_map.get(item["destination_id"]))
            for item in orders
        ]
        platform_accounts = self.list_platform_accounts()
        platform_currencies = sorted({item["currency"] for item in platform_accounts})
        consolidated_platform_balances = {
            currency: _display_amount(sum(
                int(Decimal(str(item["balance"])) * 100)
                for item in platform_accounts if item["currency"] == currency
            ))
            for currency in platform_currencies
        }
        currencies = sorted({item["currency"] for item in revenues})
        balances = {}
        for currency in currencies:
            payable = sum(
                int(row["amount_minor"]) for row in self._list("revenue_entries")
                if row["currency"] == currency and row["status"] == "PAYABLE"
            )
            reserved = sum(
                int(row["amount_minor"]) for row in orders
                if row["currency"] == currency and row["status"] in ACTIVE_PAYOUT_STATES
            )
            received = sum(
                int(row["amount_minor"]) for row in orders
                if row["currency"] == currency and row["status"] == "PAID"
            )
            balances[currency] = {
                "reported": _display_amount(sum(
                    int(row["amount_minor"]) for row in self._list("revenue_entries")
                    if row["currency"] == currency and row["status"] == "REPORTED"
                )),
                "payable": _display_amount(payable),
                "reserved_for_payout": _display_amount(reserved),
                "available_to_request": _display_amount(max(0, payable - reserved - received)),
                "payouts_marked_paid": _display_amount(received),
            }
        return {
            "architecture": {
                "nexus_owned_wallet": False,
                "funds_custodied_by_nexus": False,
                "platform_account_balances_are_external": True,
                "payout_destination": "EXTERNAL_PREPAID_VISA",
                "platform_balances_are_snapshots_not_nexus_assets": True,
            },
            "capabilities": {
                "automatic_transfer_enabled": False,
                "card_pan_or_cvv_stored": False,
                "provider_integration_required": True,
                "income_requires_evidence_to_be_payable": True,
            },
            "consolidated_platform_balances": consolidated_platform_balances,
            "platform_accounts": platform_accounts,
            "balances": balances,
            "destinations": destinations,
            "revenues": revenues,
            "payouts": payouts,
        }
