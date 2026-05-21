import logging
import requests
import base64
from django.conf import settings

logger = logging.getLogger(__name__)


class MonnifyError(Exception):
    pass


class MonnifyService:
    BASE_URL = "https://api.monnify.com/api/v1"
    TIMEOUT = 30

    @classmethod
    def _get_headers(cls):
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded = base64.b64encode(auth_str.encode()).decode()
        resp = requests.post(
            f"{cls.BASE_URL}/auth/login",
            headers={"Authorization": f"Basic {encoded}"},
            timeout=cls.TIMEOUT,
        )
        data = resp.json()
        token = data["responseBody"]["accessToken"]
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @classmethod
    def create_reserved_account(cls, user):
        headers = cls._get_headers()
        url = "https://api.monnify.com/api/v2/bank-transfer/reserved-accounts"
        payload = {
            "accountReference": f"TIC-{user.id}",
            "accountName": f"{user.first_name} {user.last_name}",
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "customerEmail": user.email,
            "customerName": f"{user.first_name} {user.last_name}",
            "getAllAvailableBanks": True,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=cls.TIMEOUT)
        resp.raise_for_status()
        body = resp.json()

        if not body.get("requestSuccessful"):
            raise MonnifyError(
                f"Monnify request failed: {body.get('responseMessage', 'Unknown error')}"
            )

        accounts = body["responseBody"].get("accounts", [])
        if not accounts:
            raise MonnifyError("Monnify returned no bank accounts")

        return {
            "bank_name": accounts[0]["bankName"],
            "account_number": accounts[0]["accountNumber"],
            "account_reference": body["responseBody"]["accountReference"],
        }
