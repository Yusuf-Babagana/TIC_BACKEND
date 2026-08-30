import logging

import requests
from django.conf import settings
from django.db import transaction as db_transaction

logger = logging.getLogger(__name__)


class NellobytesError(Exception):
    pass


class NellobytesService:
    BASE_URL = "https://www.nellobytesystems.com"
    TIMEOUT = 30

    NETWORK_CODES = {
        "MTN": "01",
        "GLO": "02",
        "T2MOBILE": "03",
        "AIRTEL": "04",
    }

    CABLE_TV_CODES = {
        "DSTV": "dstv",
        "GOTV": "gotv",
        "STARTIMES": "startimes",
        "SHOWMAX": "showmax",
    }

    # Nellobytes' own numeric codes. Deliberately NOT the same as
    # vtu/providers.py's PROVIDERS["electricity"] (CheapDataHub's scheme) —
    # the two providers assign different numbers to the same discos. Aliases
    # for CheapDataHub's naming (KADUNA/PHED/JED/YOLA/BENIN) are included so
    # the reseller endpoint's existing disco_id-based contract still resolves
    # correctly after translation via providers.disco_name_from_id().
    ELECTRIC_COMPANY_CODES = {
        "EKEDC": "01",
        "IKEDC": "02",
        "AEDC": "03",
        "KEDC": "04",
        "PHEDC": "05", "PHED": "05",
        "JEDC": "06", "JED": "06",
        "IBEDC": "07",
        "KAEDC": "08", "KADUNA": "08",
        "EEDC": "09",
        "BEDC": "10", "BENIN": "10",
        "YEDC": "11", "YOLA": "11",
        "APLE": "12",
    }

    METER_TYPE_CODES = {
        "PREPAID": "01",
        "POSTPAID": "02",
    }

    @classmethod
    def _credentials(cls):
        return settings.NELLOBYTES_USER_ID, settings.NELLOBYTES_API_KEY

    @classmethod
    def _get_json(cls, endpoint, params, timeout=None):
        try:
            resp = requests.get(f"{cls.BASE_URL}{endpoint}", params=params, timeout=timeout or cls.TIMEOUT)
            return resp.json()
        except requests.Timeout:
            raise NellobytesError("Nellobytes request timed out")
        except requests.ConnectionError:
            raise NellobytesError("Nellobytes connection failed")
        except ValueError:
            logger.error(
                "Nellobytes non-JSON response: endpoint=%s status=%s body=%s",
                endpoint, resp.status_code, resp.text[:500],
            )
            raise NellobytesError(f"Nellobytes returned invalid response (HTTP {resp.status_code})")

    @classmethod
    def _submit_order(cls, endpoint, params):
        body = cls._get_json(endpoint, params)
        order_status = body.get("status")
        if order_status != "ORDER_RECEIVED":
            logger.error("Nellobytes order rejected: endpoint=%s body=%s", endpoint, body)
            raise NellobytesError(order_status or "Nellobytes request failed")

        # Preserve any extra fields the provider includes on the initial
        # response (e.g. electricity's meterno/metertoken) alongside the
        # normalized order_id/status_code/status keys every caller relies on.
        result = dict(body)
        result["order_id"] = body.get("orderid")
        result["status_code"] = body.get("statuscode")
        result["status"] = order_status
        return result

    @classmethod
    def buy_data(cls, network, plan_id, mobile_number, request_id, callback_url):
        network_code = cls.NETWORK_CODES.get((network or "").upper())
        if not network_code:
            raise NellobytesError(f"Unsupported network for Nellobytes: {network}")

        user_id, api_key = cls._credentials()
        params = {
            "UserID": user_id,
            "APIKey": api_key,
            "MobileNetwork": network_code,
            "DataPlan": plan_id,
            "MobileNumber": mobile_number,
            "RequestID": request_id,
            "CallBackURL": callback_url,
        }
        return cls._submit_order("/APIDatabundleV1.asp", params)

    @classmethod
    def buy_airtime(cls, network, amount, mobile_number, request_id, callback_url, bonus_type=None):
        network_code = cls.NETWORK_CODES.get((network or "").upper())
        if not network_code:
            raise NellobytesError(f"Unsupported network for Nellobytes: {network}")

        user_id, api_key = cls._credentials()
        params = {
            "UserID": user_id,
            "APIKey": api_key,
            "MobileNetwork": network_code,
            "Amount": amount,
            "MobileNumber": mobile_number,
            "RequestID": request_id,
            "CallBackURL": callback_url,
        }
        if bonus_type:
            params["BonusType"] = bonus_type
        return cls._submit_order("/APIAirtimeV1.asp", params)

    @classmethod
    def buy_cable(cls, cable_tv, package, smartcard_no, phone_no, request_id, callback_url):
        cable_code = cls.CABLE_TV_CODES.get((cable_tv or "").upper())
        if not cable_code:
            raise NellobytesError(f"Unsupported CableTV provider for Nellobytes: {cable_tv}")

        user_id, api_key = cls._credentials()
        params = {
            "UserID": user_id,
            "APIKey": api_key,
            "CableTV": cable_code,
            "Package": package,
            "SmartCardNo": smartcard_no,
            "PhoneNo": phone_no,
            "RequestID": request_id,
            "CallBackURL": callback_url,
        }
        return cls._submit_order("/APICableTVV1.asp", params)

    @classmethod
    def verify_smartcard(cls, cable_tv, smartcard_no):
        cable_code = cls.CABLE_TV_CODES.get((cable_tv or "").upper())
        if not cable_code:
            raise NellobytesError(f"Unsupported CableTV provider for Nellobytes: {cable_tv}")

        user_id, api_key = cls._credentials()
        params = {
            "UserID": user_id,
            "APIKey": api_key,
            "CableTV": cable_code,
            "SmartCardNo": smartcard_no,
        }
        body = cls._get_json("/APIVerifyCableTVV1.asp", params)
        customer_name = body.get("customer_name")
        if not customer_name or customer_name == "INVALID_SMARTCARDNO":
            raise NellobytesError("INVALID_SMARTCARDNO")
        return customer_name

    @classmethod
    def buy_electricity(cls, company, meter_type, meter_no, amount, phone_no, request_id, callback_url):
        company_code = cls.ELECTRIC_COMPANY_CODES.get((company or "").upper())
        if not company_code:
            raise NellobytesError(f"Unsupported electricity company for Nellobytes: {company}")
        meter_type_code = cls.METER_TYPE_CODES.get((meter_type or "PREPAID").upper())
        if not meter_type_code:
            raise NellobytesError(f"Unsupported meter type for Nellobytes: {meter_type}")

        user_id, api_key = cls._credentials()
        params = {
            "UserID": user_id,
            "APIKey": api_key,
            "ElectricCompany": company_code,
            "MeterType": meter_type_code,
            "MeterNo": meter_no,
            "Amount": amount,
            "PhoneNo": phone_no,
            "RequestID": request_id,
            "CallBackURL": callback_url,
        }
        return cls._submit_order("/APIElectricityV1.asp", params)

    @classmethod
    def verify_meter(cls, company, meter_no, meter_type):
        company_code = cls.ELECTRIC_COMPANY_CODES.get((company or "").upper())
        if not company_code:
            raise NellobytesError(f"Unsupported electricity company for Nellobytes: {company}")
        meter_type_code = cls.METER_TYPE_CODES.get((meter_type or "PREPAID").upper())
        if not meter_type_code:
            raise NellobytesError(f"Unsupported meter type for Nellobytes: {meter_type}")

        user_id, api_key = cls._credentials()
        params = {
            "UserID": user_id,
            "APIKey": api_key,
            "ElectricCompany": company_code,
            "MeterNo": meter_no,
            "MeterType": meter_type_code,
        }
        body = cls._get_json("/APIVerifyElectricityV1.asp", params)
        customer_name = body.get("customer_name")
        if not customer_name or customer_name == "INVALID_METERNO":
            raise NellobytesError("INVALID_METERNO")
        return customer_name

    @classmethod
    def get_wallet_balance(cls, timeout=20):
        """
        Checks *our* reseller balance on Nellobytes, not any end user's
        wallet — this is what the admin dashboard funds so purchases keep
        working. Uses a shorter-than-default timeout since callers typically
        block a page render on this, but still generous enough that a merely
        slow (not down) provider doesn't read as "Unavailable".

        Retries once on failure: this is a plain read (no wallet debit, no
        order placed), so a retry can't double-charge anything, and Nellobytes
        has been observed to return a transient INVALID_CREDENTIALS-shaped
        failure that clears up on the very next call with the same
        credentials — confirmed 2026-08-30, live account, same UserID/APIKey
        succeeded on retry seconds later.
        """
        user_id, api_key = cls._credentials()
        params = {"UserID": user_id, "APIKey": api_key}

        last_error = None
        for attempt in range(2):
            try:
                body = cls._get_json("/APIWalletBalanceV1.asp", params, timeout=timeout)
            except NellobytesError as e:
                last_error = e
                continue

            balance = body.get("balance")
            if balance is not None:
                return body

            last_error = NellobytesError(body.get("status") or "UNKNOWN_ERROR")
            logger.warning(
                "Nellobytes wallet balance check failed (attempt %s/2): %s", attempt + 1, body,
            )

        logger.error("Nellobytes wallet balance check failed after retry: %s", last_error)
        raise last_error

    @classmethod
    def query_order(cls, order_id=None, request_id=None):
        user_id, api_key = cls._credentials()
        params = {"UserID": user_id, "APIKey": api_key}
        if order_id:
            params["OrderID"] = order_id
        elif request_id:
            params["RequestID"] = request_id
        else:
            raise NellobytesError("query_order requires order_id or request_id")

        return cls._get_json("/APIQueryV1.asp", params)

    @staticmethod
    def resolve_order_outcome(orderstatus, statuscode=None):
        """
        Best-effort heuristic — Nellobytes' docs only confirm ORDER_COMPLETED
        (statuscode=200) as a terminal success and ORDER_CANCELLED as a
        terminal failure/cancel; ORDER_ONHOLD is a known intermediate state
        (cable docs: only ORDER_RECEIVED/ORDER_ONHOLD orders are cancellable)
        and correctly falls through to PENDING here. Tighten this once the
        full final-status code table is available.
        """
        value = (orderstatus or "").upper()
        if "COMPLETED" in value:
            return "SUCCESSFUL"
        if "FAILED" in value or "REFUND" in value or "CANCEL" in value:
            return "FAILED"
        return "PENDING"

    @staticmethod
    def apply_order_outcome(transaction_id, outcome):
        """
        Race-safe, idempotent. Locks the Transaction row first, then the
        Wallet row (in that order, consistently), inside one atomic block —
        prevents a double refund if the webhook and a reconciliation sweep
        both resolve the same order concurrently.
        """
        from wallet.models import Transaction, Wallet

        with db_transaction.atomic():
            try:
                txn = Transaction.objects.select_for_update().get(pk=transaction_id)
            except Transaction.DoesNotExist:
                logger.error("apply_order_outcome: Transaction %s not found", transaction_id)
                return

            if txn.status != "PENDING":
                logger.info(
                    "apply_order_outcome: Transaction %s already resolved (%s) — skipping",
                    transaction_id, txn.status,
                )
                return

            if outcome == "SUCCESSFUL":
                txn.status = "SUCCESSFUL"
                txn.save(update_fields=["status"])

                # dashboard's transaction_made signal only fires on Transaction
                # *creation* with status already SUCCESSFUL — this txn was created
                # PENDING, so replicate that admin notification here to keep parity
                # with the synchronous CheapDataHub purchase flow.
                from dashboard.models import AdminNotification
                AdminNotification.objects.create(
                    notification_type="new_purchase",
                    message=f"Purchase: {txn.user.username} bought ₦{txn.amount} ({txn.trans_type}) — {txn.reference}",
                    link="/dashboard/transactions/",
                )

                from users.utils import reward_referrer_on_first_purchase
                reward_referrer_on_first_purchase(txn.user)
            elif outcome == "FAILED":
                wallet = Wallet.objects.select_for_update().get(user=txn.user)
                wallet.balance += txn.amount
                wallet.save(update_fields=["balance"])
                txn.status = "FAILED"
                txn.save(update_fields=["status"])
            else:
                logger.warning(
                    "apply_order_outcome: Transaction %s outcome still PENDING/unrecognized — needs manual review",
                    transaction_id,
                )
