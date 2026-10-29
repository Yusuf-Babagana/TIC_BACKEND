"""
Transaction engine: idempotency -> reserve funds -> route -> submit -> (failover
only when provably safe) -> settle/refund. Provider specifics never appear here.

Failover rule (the money-safety core): the next provider is tried ONLY after the
previous one returned REJECTED for a provider-side reason
(``ProviderResult.failover_safe``). ACCEPTED stops the loop; AMBIGUOUS (timeout,
dropped connection, odd reply) also stops it and leaves the transaction PENDING
for reconciliation, because the order may exist. Funds are refunded only after
every attempt is a confirmed REJECTED, or the provider confirms the order failed.
"""
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from vtu.models import PurchaseAttempt
from wallet.models import Transaction

from . import health, ledger, registry, router
from .types import ErrorCategory, OrderStatus, Outcome, ProviderResult, PurchaseRequest, Service

logger = logging.getLogger("vtu.gateway")

MAINTENANCE_MESSAGE = "This service is temporarily under maintenance. Please try again shortly."
# A PENDING transaction with no live attempt is only refunded after this long, so a
# purchase still mid-failover in another worker is never mistaken for an orphan.
ORPHAN_GRACE = timedelta(minutes=10)


# ---------------------------------------------------------------------------
# Purchase
# ---------------------------------------------------------------------------

def execute_purchase(user, template: PurchaseRequest, cost, idempotency_key=None):
    """Returns ``(http_status, body_dict)``. ``template.reference`` is generated here."""
    existing = ledger.find_by_idempotency_key(user, idempotency_key)
    if existing:
        return _replay(existing)

    selection = router.select(template)
    if not selection.supporting:
        return 400, {"status": "false", "message": f"Unsupported network or service: {template.network}"}
    if not selection.adapters:
        return 503, {"status": "false", "message": MAINTENANCE_MESSAGE}

    base_ref = f"TIC-{uuid.uuid4().hex[:16].upper()}"
    try:
        txn, created = ledger.reserve(user, Service.TRANSACTION_TYPE[template.service], cost, base_ref, idempotency_key)
    except ledger.InsufficientFunds:
        return 400, {"status": "false", "message": "Insufficient Balance"}
    except ledger.NoWallet:
        return 400, {"status": "false", "message": "Wallet not found"}
    if not created:
        return _replay(txn)

    last = None
    for seq, adapter in enumerate(selection.adapters, start=1):
        result = _attempt(txn, adapter, template, base_ref, seq)
        last = result

        if result.outcome == Outcome.ACCEPTED:
            health.record_success(adapter.name)
            ledger.attach_provider(txn.pk, adapter.name, result.provider_order_id)
            ledger.record_event(txn, "PENDING", "PENDING", "purchase", f"accepted by {adapter.name}")
            body = {
                "status": "pending",
                "message": f"Your {txn.trans_type.lower()} purchase is being processed",
                "reference": base_ref,
                "order_id": result.provider_order_id,
            }
            body.update(result.extra)
            return 202, body

        if result.outcome == Outcome.AMBIGUOUS:
            # May already be processed - never fail over, never refund. Reconciliation decides.
            health.record_failure(adapter.name, result.category, result.message)
            ledger.attach_provider(txn.pk, adapter.name, result.provider_order_id)
            ledger.record_event(txn, "PENDING", "PENDING", "purchase",
                                f"{adapter.name} outcome unclear ({result.category}); awaiting reconciliation")
            logger.warning("vtu ambiguous: ref=%s provider=%s category=%s", base_ref, adapter.name, result.category)
            return 202, {
                "status": "pending",
                "message": f"Your {txn.trans_type.lower()} purchase is being processed",
                "reference": base_ref,
                "order_id": result.provider_order_id or None,
            }

        # REJECTED: provider confirmed nothing was processed.
        if result.category == ErrorCategory.INVALID_REQUEST:
            health.record_success(adapter.name)     # it answered correctly; the request is the problem
        else:
            health.record_failure(adapter.name, result.category, result.message)
        if not result.failover_safe:
            break
        logger.warning("vtu failover: ref=%s provider=%s rejected (%s); trying next", base_ref, adapter.name, result.category)

    ledger.settle(txn.pk, OrderStatus.FAILED, "purchase", f"all providers rejected; last={last.code or last.category}")
    return _failure_response(last)


def _attempt(txn, adapter, template, base_ref, seq) -> ProviderResult:
    reference = base_ref if seq == 1 else f"{base_ref}-{seq}"
    request = PurchaseRequest(**{**template.__dict__, "reference": reference})
    request.callback_url = f"{settings.PUBLIC_BASE_URL}{adapter.callback_url_path()}"

    # Recorded BEFORE the network call: a crash mid-call still leaves a SUBMITTING row,
    # which reconciliation treats as a possibly-live order.
    attempt = PurchaseAttempt.objects.create(transaction=txn, provider=adapter.name, reference=reference, sequence=seq)
    try:
        result = adapter.purchase(request)
    except Exception:
        # Unexpected adapter bug: the request may or may not have left the building.
        logger.exception("vtu adapter %s crashed submitting ref=%s", adapter.name, reference)
        result = ProviderResult(Outcome.AMBIGUOUS, ErrorCategory.UNKNOWN, "ADAPTER_ERROR", "Adapter error")

    PurchaseAttempt.objects.filter(pk=attempt.pk).update(
        outcome=result.outcome, error_category=result.category, code=result.code[:100],
        message=result.message[:255], provider_order_id=result.provider_order_id[:100],
        response=result.raw, elapsed_ms=result.elapsed_ms,
    )
    logger.info("vtu attempt: ref=%s provider=%s outcome=%s category=%s ms=%s",
                reference, adapter.name, result.outcome, result.category, result.elapsed_ms)
    return result


def _failure_response(last: ProviderResult):
    if last.category == ErrorCategory.PROVIDER_BALANCE or "INSUFFICIENT_BALANCE" in (last.code or "").upper():
        # Our float at the provider ran dry: an operational issue, not the customer's wallet.
        return 503, {"status": "false", "message": MAINTENANCE_MESSAGE}
    return 502, {"status": "false", "message": last.message or "Service temporarily unavailable. Please try again."}


def _replay(txn):
    """Response for a repeated request carrying an already-used idempotency key."""
    body = {"reference": txn.reference, "order_id": txn.order_id, "idempotent_replay": True}
    if txn.status == "PENDING":
        return 202, {**body, "status": "pending", "message": f"Your {txn.trans_type.lower()} purchase is being processed"}
    if txn.status == "SUCCESSFUL":
        return 200, {**body, "status": "successful", "message": "Purchase completed"}
    return 409, {**body, "status": "false", "message": "This purchase did not go through and was refunded"}


# ---------------------------------------------------------------------------
# Resolution: webhook / polling / sweep all converge on settle()
# ---------------------------------------------------------------------------

def apply_outcome(transaction_id, outcome, source="reconcile"):
    """Legacy-compatible entry point: outcome is 'SUCCESSFUL' or 'FAILED'."""
    return ledger.settle(transaction_id, outcome, source)


def _live_attempts(txn):
    return [a for a in txn.attempts.all()
            if a.outcome in (Outcome.ACCEPTED, Outcome.AMBIGUOUS, PurchaseAttempt.SUBMITTING)]


def reconcile_transaction(txn, source="reconcile"):
    """
    Ask the provider(s) holding a possibly-live order what happened, and settle only
    on a definite answer. Never refunds on UNKNOWN/PENDING/query errors.
    Returns the transaction's resulting status.
    """
    txn.refresh_from_db()
    if txn.status != "PENDING":
        return txn.status

    live = _live_attempts(txn)
    if not live and txn.order_id:
        # Pre-gateway transaction: no attempt rows, only an order id from the original provider.
        live = [PurchaseAttempt(provider=txn.provider or "nellobytes", reference=txn.reference,
                                provider_order_id=txn.order_id)]

    if not live:
        # No submission ever reached a provider (or every one was a confirmed rejection) and a
        # worker died before refunding. Safe to refund once it is clearly not mid-flight.
        if timezone.now() - txn.created_at > ORPHAN_GRACE:
            ledger.settle(txn.pk, OrderStatus.FAILED, source, "no provider submission recorded; refunded")
        txn.refresh_from_db()
        return txn.status

    statuses = []
    for attempt in live:
        adapter = registry.get_adapter(attempt.provider)
        if adapter is None:
            statuses.append(OrderStatus.UNKNOWN)
            continue
        try:
            res = adapter.query_status(attempt.provider_order_id, attempt.reference)
        except Exception:
            logger.exception("vtu query_status crashed: provider=%s ref=%s", attempt.provider, attempt.reference)
            statuses.append(OrderStatus.UNKNOWN)
            continue
        statuses.append(res.status)

    if OrderStatus.SUCCESSFUL in statuses:
        ledger.settle(txn.pk, OrderStatus.SUCCESSFUL, source)
    elif statuses and all(s == OrderStatus.FAILED for s in statuses):
        ledger.settle(txn.pk, OrderStatus.FAILED, source)
    txn.refresh_from_db()
    return txn.status


def reconcile_pending(older_than_minutes=3):
    """Sweep PENDING VTU transactions. Returns (checked, resolved)."""
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    pending = Transaction.objects.filter(
        trans_type__in=("DATA", "AIRTIME", "UTILITY"), status="PENDING", created_at__lt=cutoff,
    )
    checked = resolved = 0
    for txn in pending:
        checked += 1
        if reconcile_transaction(txn, "reconcile") != "PENDING":
            resolved += 1
    return checked, resolved


def handle_webhook(adapter, request):
    """
    Returns ``(http_status, body, log_outcome, detail)``. A callback is a *hint*: unless the
    adapter cryptographically verified it, the real status is fetched from the provider.
    """
    from .base import WebhookRejected

    try:
        event = adapter.parse_webhook(request)
    except WebhookRejected as e:
        return 401, {"status": "rejected"}, "signature_rejected", str(e)[:200]

    ref = f"order_id={event.provider_order_id} request_id={event.reference}"
    attempt = None
    if event.reference:
        attempt = PurchaseAttempt.objects.filter(provider=adapter.name, reference=event.reference).select_related("transaction").first()
    if attempt is None and event.provider_order_id:
        attempt = PurchaseAttempt.objects.filter(provider=adapter.name, provider_order_id=event.provider_order_id).select_related("transaction").first()
    txn = attempt.transaction if attempt else None
    if txn is None:     # pre-gateway orders have no attempt rows
        if event.provider_order_id:
            txn = Transaction.objects.filter(order_id=event.provider_order_id).first()
        if txn is None and event.reference:
            txn = Transaction.objects.filter(reference=event.reference).first()
    if txn is None:
        return 404, {"status": "not_found"}, "error", f"No matching transaction - {ref}"

    if txn.status != "PENDING":
        return 200, {"status": "already_resolved"}, "duplicate_ignored", f"status={txn.status} - {ref}"

    if event.verified and event.claimed_status in (OrderStatus.SUCCESSFUL, OrderStatus.FAILED):
        ledger.settle(txn.pk, event.claimed_status, "webhook")
        return 200, {"status": "acknowledged"}, "resolved", f"outcome={event.claimed_status} (verified) - {ref}"

    status = reconcile_transaction(txn, "webhook")
    if status == "PENDING":
        return 200, {"status": "acknowledged"}, "resolved", f"still pending after provider query - {ref}"
    return 200, {"status": "acknowledged"}, "resolved", f"outcome={status} - {ref}"
