import logging

import requests

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
TIMEOUT = 10


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
