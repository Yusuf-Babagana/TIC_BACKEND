import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class CheapDataHubError(Exception):
    pass


class CheapDataHubService:
    BASE_URL = "https://www.cheapdatahub.ng/api/v1/resellers"
    TIMEOUT = 30
    PLAN_SYNC_TIMEOUT = 15

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
    def _call(cls, method, endpoint, payload=None):
        url = f"{cls.BASE_URL}{endpoint}"
        try:
            if method == "GET":
                resp = requests.get(url, headers=cls._headers(), timeout=cls.TIMEOUT)
            else:
                resp = requests.post(
                    url, json=payload, headers=cls._headers(), timeout=cls.TIMEOUT
                )
            body = resp.json()
        except requests.Timeout:
            raise CheapDataHubError("Provider request timed out")
        except requests.ConnectionError:
            raise CheapDataHubError("Provider connection failed")
        except ValueError:
            logger.error(
                "CheapDataHub non-JSON response: status=%s body=%s",
                resp.status_code, resp.text[:500],
            )
            raise CheapDataHubError(
                f"Provider returned invalid response (HTTP {resp.status_code})"
            )

        if resp.status_code != 200:
            msg = body.get("message") or body.get("error") or f"HTTP {resp.status_code}"
            raise CheapDataHubError(msg)

        return body

    CATEGORY_ENDPOINTS = {
        "DATA": "/data/purchase/",
        "AIRTIME": "/airtime/purchase/",
        "CABLE": "/cable/purchase/",
        "ELECTRICITY": "/electricity/purchase/",
    }

    @classmethod
    def purchase(cls, category, payload):
        endpoint = cls.CATEGORY_ENDPOINTS.get(category)
        if not endpoint:
            raise CheapDataHubError(f"Unsupported category: {category}")
        return cls._call("POST", endpoint, payload)

    @classmethod
    def fetch_balance(cls):
        return cls._call("GET", "/wallet/balance/")

    @classmethod
    def buy_airtime(cls, provider_id, phone_number, amount):
        return cls._call(
            "POST",
            "/airtime/purchase/",
            {"provider_id": provider_id, "phone_number": phone_number, "amount": amount},
        )

    @classmethod
    def buy_data(cls, bundle_id, phone_number):
        return cls._call(
            "POST",
            "/data/purchase/",
            {"bundle_id": bundle_id, "phone_number": phone_number},
        )

    @classmethod
    def buy_electricity(cls, disco_id, meter_number, amount, meter_type, phone):
        return cls._call(
            "POST",
            "/electricity/purchase/",
            {
                "disco_id": disco_id,
                "meter_number": meter_number,
                "amount": amount,
                "meter_type": meter_type,
                "phone": phone,
            },
        )

    @classmethod
    def buy_cable(cls, plan_id, card_number, phone):
        return cls._call(
            "POST",
            "/cable/purchase/",
            {"plan_id": plan_id, "card_number": card_number, "phone": phone},
        )

    @classmethod
    def buy_exam_pin(cls, product_id, quantity):
        return cls._call(
            "POST",
            "/exam-pin/purchase/",
            {"product_id": product_id, "quantity": quantity},
        )

    @classmethod
    def sync_live_plans(cls):
        from vtu.models import DataPlan

        url = f"{cls.BASE_URL}/data/plans/"
        try:
            resp = requests.get(url, headers=cls._headers(), timeout=cls.PLAN_SYNC_TIMEOUT)
            if resp.status_code != 200:
                logger.error("Plan sync failed: HTTP %s %s", resp.status_code, resp.text)
                return False
            plans_data = resp.json().get("data", [])
            if not plans_data:
                logger.warning("Plan sync returned empty data set")
                return False

            DataPlan.objects.all().update(is_active=False)

            for plan in plans_data:
                DataPlan.objects.update_or_create(
                    plan_id=plan["plan_id"],
                    defaults={
                        "network": plan["network"].upper(),
                        "plan_name": plan["name"],
                        "price": plan["price"],
                        "is_active": True,
                    },
                )
            logger.info("Plan sync completed: %d plans loaded", len(plans_data))
            return True
        except requests.Timeout:
            logger.error("Plan sync timed out")
        except requests.ConnectionError:
            logger.error("Plan sync connection failed")
        except Exception:
            logger.exception("Plan sync unexpected error")
        return False
