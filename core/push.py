import logging

import requests

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
TIMEOUT = 10
# Expo rejects a single request with more than 100 messages.
BATCH_SIZE = 100


def send_push_notification(push_token, title, body, data=None):
    """
    Best-effort delivery of a single push notification via Expo's push service.
    Never raises — a failure here must never break the caller's own operation
    (e.g. crediting a wallet deposit). Returns True/False for whether Expo
    accepted the request.
    """
    if not push_token or not push_token.startswith(("ExponentPushToken[", "ExpoPushToken[")):
        return False

    payload = {
        "to": push_token,
        "title": title,
        "body": body,
        "sound": "default",
    }
    if data:
        payload["data"] = data

    try:
        resp = requests.post(
            EXPO_PUSH_URL,
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        result = resp.json()
        ticket = result.get("data") or {}
        if isinstance(ticket, dict) and ticket.get("status") == "error":
            logger.warning("Expo push rejected token=%s: %s", push_token, ticket)
            return False
        return True
    except Exception as e:
        logger.error("Failed to send push notification to %s: %s", push_token, e)
        return False


def send_push_notifications_bulk(messages):
    """
    Best-effort delivery of many push notifications (e.g. an admin broadcast) via Expo's
    push service, chunked into Expo's 100-per-request limit. Never raises. Each item in
    `messages` is a dict with at least "to", "title", "body" (Expo's message shape).
    Returns how many messages Expo accepted (not proof of final device delivery — Expo's
    receipts API would be needed for that, which isn't worth the complexity here).
    """
    valid = [m for m in messages if (m.get("to") or "").startswith(("ExponentPushToken[", "ExpoPushToken["))]
    accepted = 0

    for i in range(0, len(valid), BATCH_SIZE):
        batch = valid[i:i + BATCH_SIZE]
        try:
            resp = requests.post(
                EXPO_PUSH_URL,
                json=batch,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            result = resp.json()
            tickets = result.get("data") or []
            for ticket in tickets:
                if isinstance(ticket, dict) and ticket.get("status") == "error":
                    logger.warning("Expo push rejected in batch: %s", ticket)
                else:
                    accepted += 1
        except Exception as e:
            logger.error("Failed to send push notification batch (%d messages): %s", len(batch), e)

    return accepted
