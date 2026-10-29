"""
All wallet money movement for VTU purchases goes through here, so there is one
place that guarantees:

* a debit and its Transaction row are created together or not at all;
* the same ``Idempotency-Key`` never debits twice;
* status moves only along allowed edges, under a row lock, each leaving a
  ``TransactionEvent``;
* a refund happens at most once (``Transaction.refunded_at`` + the status guard).

Lock order: ``settle`` locks Transaction then Wallet (as the original code did);
``reserve`` only ever locks the Wallet, so the two cannot deadlock.
"""
import logging
from decimal import Decimal

from django.db import IntegrityError, transaction as db
from django.utils import timezone

from wallet.models import Transaction, TransactionEvent, Wallet

from .types import OrderStatus

logger = logging.getLogger("vtu.gateway")


class InsufficientFunds(Exception):
    pass


class NoWallet(Exception):
    pass


def record_event(txn, from_status, to_status, source, detail="", delta=Decimal("0"), balance_after=None):
    TransactionEvent.objects.create(
        transaction=txn, from_status=from_status or "", to_status=to_status,
        wallet_delta=delta, balance_after=balance_after, source=source, detail=detail[:255],
    )


def find_by_idempotency_key(user, key):
    if not key:
        return None
    return Transaction.objects.filter(user=user, idempotency_key=key).first()


def reserve(user, trans_type, cost, reference, idempotency_key=None):
    """
    Debit the wallet and create the PENDING Transaction atomically.
    Returns ``(transaction, created)``; ``created`` is False when the idempotency
    key already belongs to a transaction (no money moved).
    """
    cost = Decimal(str(cost))
    with db.atomic():
        try:
            wallet = Wallet.objects.select_for_update().get(user=user)
        except Wallet.DoesNotExist:
            raise NoWallet()

        existing = find_by_idempotency_key(user, idempotency_key)
        if existing:
            return existing, False
        if wallet.balance < cost:
            raise InsufficientFunds()

        try:
            with db.atomic():   # savepoint: a unique-key race must undo the debit too
                wallet.balance -= cost
                wallet.save(update_fields=["balance"])
                txn = Transaction.objects.create(
                    user=user, trans_type=trans_type, amount=cost, reference=reference,
                    status="PENDING", idempotency_key=idempotency_key or None,
                )
                record_event(txn, "", "PENDING", "purchase", "wallet debited", -cost, wallet.balance)
        except IntegrityError:
            existing = find_by_idempotency_key(user, idempotency_key)
            if existing:
                return existing, False
            raise
        return txn, True


def attach_provider(txn_id, provider, order_id=""):
    fields = {"provider": provider}
    if order_id:
        fields["order_id"] = order_id
    Transaction.objects.filter(pk=txn_id).update(**fields)


def _refund_locked(txn, source, detail):
    """Caller holds the Transaction row lock and txn.status is PENDING."""
    wallet = Wallet.objects.select_for_update().get(user=txn.user)
    old = txn.status
    delta = Decimal("0")
    if txn.refunded_at is None:
        wallet.balance += txn.amount
        wallet.save(update_fields=["balance"])
        txn.refunded_at = timezone.now()
        delta = txn.amount
    txn.status = "FAILED"
    txn.save(update_fields=["status", "refunded_at"])
    record_event(txn, old, "FAILED", source, detail or "refunded", delta, wallet.balance)


def settle(transaction_id, outcome, source, detail=""):
    """
    Apply a *confirmed* provider outcome (OrderStatus.SUCCESSFUL / FAILED) to a
    PENDING transaction. Idempotent and race-safe; returns True only for the call
    that actually changed the transaction.
    """
    notify = False
    with db.atomic():
        try:
            txn = Transaction.objects.select_for_update().select_related("user").get(pk=transaction_id)
        except Transaction.DoesNotExist:
            logger.error("settle: transaction %s not found", transaction_id)
            return False

        if txn.status != "PENDING":
            if outcome == OrderStatus.SUCCESSFUL and txn.status in ("FAILED", "REFUNDED"):
                # Provider says delivered after we already refunded: money-losing, needs a human.
                logger.critical("VTU ANOMALY: txn %s is %s but provider reports SUCCESS", txn.reference, txn.status)
                record_event(txn, txn.status, txn.status, source, "ANOMALY: provider reports success after refund")
            else:
                logger.info("settle: txn %s already %s - ignoring %s", txn.reference, txn.status, outcome)
            return False

        if outcome == OrderStatus.SUCCESSFUL:
            txn.status = "SUCCESSFUL"
            txn.save(update_fields=["status"])
            record_event(txn, "PENDING", "SUCCESSFUL", source, detail or "provider confirmed")
            notify = True
        elif outcome == OrderStatus.FAILED:
            _refund_locked(txn, source, detail or "provider confirmed failure; wallet refunded")
        else:
            logger.warning("settle: txn %s outcome %s is not final - left PENDING", txn.reference, outcome)
            return False

    if notify:
        _after_success(txn)
    return True


def _after_success(txn):
    # Side effects must never undo or block the status change.
    try:
        from dashboard.models import AdminNotification
        AdminNotification.objects.create(
            notification_type="new_purchase",
            message=f"Purchase: {txn.user.username} bought ₦{txn.amount} ({txn.trans_type}) - {txn.reference}",
            link="/dashboard/transactions/",
        )
        from users.utils import reward_referrer_on_first_purchase
        reward_referrer_on_first_purchase(txn.user)
    except Exception:
        logger.exception("post-success side effects failed for txn %s", txn.reference)
