import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class CheapDataHubError(Exception):
    pass


class CheapDataHubService:
    BASE_URL = "https://www.cheapdatahub.ng/api/v1/resellers"
    TIMEOUT = 30

    @classmethod
    def _headers(cls):
        api_key = settings.CHEAPDATAHUB_API_KEY
        if not api_key or api_key == "YOUR_NEW_REGENERATED_KEY_HERE":
            logger.warning("CHEAPDATAHUB_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def get_balance(cls):
        url = f"{cls.BASE_URL}/wallet/balance/"
        resp = requests.get(url, headers=cls._headers(), timeout=cls.TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def purchase_airtime(cls, provider_id, phone_number, amount):
        url = f"{cls.BASE_URL}/airtime/purchase/"
        payload = {
            "provider_id": provider_id,
            "phone_number": phone_number,
            "amount": amount,
        }
        resp = requests.post(
            url, json=payload, headers=cls._headers(), timeout=cls.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def purchase_data(cls, bundle_id, phone_number):
        url = f"{cls.BASE_URL}/data/purchase/"
        payload = {"bundle_id": bundle_id, "phone_number": phone_number}
        resp = requests.post(
            url, json=payload, headers=cls._headers(), timeout=cls.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def purchase_electricity(cls, disco_id, meter_number, amount, meter_type, phone):
        url = f"{cls.BASE_URL}/electricity/purchase/"
        payload = {
            "disco_id": disco_id,
            "meter_number": meter_number,
            "amount": amount,
            "meter_type": meter_type,
            "phone": phone,
        }
        resp = requests.post(
            url, json=payload, headers=cls._headers(), timeout=cls.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def purchase_cable(cls, plan_id, card_number, phone):
        url = f"{cls.BASE_URL}/cable/purchase/"
        payload = {"plan_id": plan_id, "card_number": card_number, "phone": phone}
        resp = requests.post(
            url, json=payload, headers=cls._headers(), timeout=cls.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def purchase_exam_pin(cls, product_id, quantity):
        url = f"{cls.BASE_URL}/exam-pin/purchase/"
        payload = {"product_id": product_id, "quantity": quantity}
        resp = requests.post(
            url, json=payload, headers=cls._headers(), timeout=cls.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()
