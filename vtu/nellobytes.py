import logging

import requests

logger = logging.getLogger(__name__)


class NellobytesError(Exception):
    """
    ``ambiguous`` is True when the request may have reached Nellobytes and been
    processed (read timeout, dropped connection, unparseable reply) - callers
    must NOT treat that as a failed order. ``code`` is Nellobytes' raw status
    string when it answered with a rejection.
    """

    def __init__(self, message="", ambiguous=False, code=""):
        super().__init__(message)
        self.ambiguous = ambiguous
        self.code = code


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
    def _config(cls):
        from vtu.gateway.adapters.nellobytes import load_config
        return load_config()

    @classmethod
    def _credentials(cls):
        cfg = cls._config()
        return cfg.get("USER_ID"), cfg.get("API_KEY")

    @classmethod
    def _base_url(cls):
        return cls._config().get("BASE_URL", cls.BASE_URL).rstrip("/")

    @classmethod
    def _timeout(cls):
        try:
            return float(cls._config().get("TIMEOUT", cls.TIMEOUT))
        except ValueError:
            return cls.TIMEOUT

    @classmethod
    def _get_json(cls, endpoint, params, timeout=None):
        # Exception text from requests embeds the full URL (credentials are in
        # the query string), so never log or re-raise it - only fixed messages.
        try:
            resp = requests.get(
                f"{cls._base_url()}{endpoint}", params=params, timeout=timeout or cls._timeout()
            )
        except requests.ConnectTimeout:
            # No connection was ever established, so nothing was sent.
            raise NellobytesError("Nellobytes request timed out", code="CONNECT_TIMEOUT")
        except requests.Timeout:
            raise NellobytesError("Nellobytes request timed out", ambiguous=True, code="TIMEOUT")
        except requests.ConnectionError:
            raise NellobytesError("Nellobytes connection failed", ambiguous=True, code="CONNECTION")

        try:
            return resp.json()
        except ValueError:
            logger.error(
                "Nellobytes non-JSON response: endpoint=%s status=%s", endpoint, resp.status_code,
            )
            raise NellobytesError(
                f"Nellobytes returned invalid response (HTTP {resp.status_code})",
                ambiguous=True, code="BAD_RESPONSE",
            )

    # Statuses Nellobytes has returned for a request that never actually
    # reached order processing — either their own docs describe them as an
    # undifferentiated internal fault (INVALID_API_ERROR1/2: "API error.",
    # no further detail — see clubkonnect.com's dispute-resolution status
    # table) or it's the exact status that was already confirmed transient
    # for a valid UserID/APIKey combo (INVALID_CREDENTIALS — see
    # WALLET_BALANCE_RETRY_DELAYS above, 2026-08-30). Safe to retry: none of
    # these mean the order was received, so a retry can't double-submit it.
    # Deterministic rejections (bad recipient/amount/network, insufficient
    # balance, real credential/access problems) are NOT in this set — retrying
    # those would only delay a failure the same params will always produce.
    RETRYABLE_ORDER_STATUSES = {"INVALID_API_ERROR1", "INVALID_API_ERROR2", "INVALID_CREDENTIALS"}
    # Only ONE retry, with a short timeout — not the wallet-balance check's
    # 3-attempt/30s-timeout budget. That combination (up to 3x cls.TIMEOUT
    # plus sleep) was observed in practice to push total request time past
    # the mobile client's 30s axios timeout and PythonAnywhere's own proxy
    # timeout when the underlying failure wasn't actually transient (e.g. a
    # genuinely broken API key) — the connection gets killed mid-retry and
    # the client sees a raw "Network Error" instead of a clean failure
    # response. The first attempt keeps the full cls.TIMEOUT in case it's a
    # legitimately slow (not broken) order; the retry doesn't need that much
    # since a fast rejection just came back on attempt 1.
    ORDER_RETRY_DELAY = 2
    ORDER_RETRY_TIMEOUT = 10

    @classmethod
    def _submit_order(cls, endpoint, params):
        import time

        attempts = 2
        for attempt in range(attempts):
            if attempt == 0:
                body = cls._get_json(endpoint, params)
            else:
                time.sleep(cls.ORDER_RETRY_DELAY)
                body = cls._get_json(endpoint, params, timeout=cls.ORDER_RETRY_TIMEOUT)

            order_status = body.get("status")

            if order_status == "ORDER_RECEIVED":
                # Preserve any extra fields the provider includes on the initial
                # response (e.g. electricity's meterno/metertoken) alongside the
                # normalized order_id/status_code/status keys every caller relies on.
                result = dict(body)
                result["order_id"] = body.get("orderid")
                result["status_code"] = body.get("statuscode")
                result["status"] = order_status
                return result

            # An ORDER_* status (e.g. ORDER_ONHOLD) or any reply carrying an orderid means
            # an order may exist on their side - that is NOT a rejection, so flag it
            # ambiguous and let status reconciliation decide (never refund blindly).
            if (body.get("orderid") or str(order_status or "").startswith("ORDER_")) and                     order_status not in cls.RETRYABLE_ORDER_STATUSES:
                logger.warning("Nellobytes non-RECEIVED status with order: endpoint=%s status=%s", endpoint, order_status)
                err = NellobytesError(order_status or "Nellobytes order state unclear", ambiguous=True, code=order_status or "")
                err.order_id = body.get("orderid") or ""
                raise err

            if order_status not in cls.RETRYABLE_ORDER_STATUSES:
                logger.error("Nellobytes order rejected: endpoint=%s status=%s", endpoint, order_status)
                raise NellobytesError(order_status or "Nellobytes request failed", code=order_status or "")

            logger.warning(
                "Nellobytes order status %s (attempt %s/%s), retrying: endpoint=%s",
                order_status, attempt + 1, attempts, endpoint,
            )

        logger.error("Nellobytes order rejected after %s attempts: endpoint=%s status=%s", attempts, endpoint, order_status)
        raise NellobytesError(order_status or "Nellobytes request failed", code=order_status or "")

    @classmethod
    def buy_data(cls, network, plan_id, mobile_number, request_id, callback_url):
        network_code = cls.NETWORK_CODES.get((network or "").upper())
        if not network_code:
            raise NellobytesError(f"Unsupported network for Nellobytes: {network}", code="UNSUPPORTED")

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
            raise NellobytesError(f"Unsupported network for Nellobytes: {network}", code="UNSUPPORTED")

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
            raise NellobytesError(f"Unsupported CableTV provider for Nellobytes: {cable_tv}", code="UNSUPPORTED")

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
            raise NellobytesError(f"Unsupported CableTV provider for Nellobytes: {cable_tv}", code="UNSUPPORTED")

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
            raise NellobytesError(f"Unsupported electricity company for Nellobytes: {company}", code="UNSUPPORTED")
        meter_type_code = cls.METER_TYPE_CODES.get((meter_type or "PREPAID").upper())
        if not meter_type_code:
            raise NellobytesError(f"Unsupported meter type for Nellobytes: {meter_type}", code="UNSUPPORTED")

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
            raise NellobytesError(f"Unsupported electricity company for Nellobytes: {company}", code="UNSUPPORTED")
        meter_type_code = cls.METER_TYPE_CODES.get((meter_type or "PREPAID").upper())
        if not meter_type_code:
            raise NellobytesError(f"Unsupported meter type for Nellobytes: {meter_type}", code="UNSUPPORTED")

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

    # Delay before each retry of get_wallet_balance, in seconds. A back-to-back
    # immediate retry (0s) turned out not to be enough — the observed
    # INVALID_CREDENTIALS blips on Nellobytes' side outlast a single network
    # round trip, so later attempts wait a bit longer to actually land outside
    # the blip window instead of just repeating the same failure instantly.
    WALLET_BALANCE_RETRY_DELAYS = (1.5, 3)

    @classmethod
    def get_wallet_balance(cls, timeout=20):
        """
        Checks *our* reseller balance on Nellobytes, not any end user's
        wallet — this is what the admin dashboard funds so purchases keep
        working. Uses a shorter-than-default timeout since callers typically
        block a page render on this, but still generous enough that a merely
        slow (not down) provider doesn't read as "Unavailable".

        Retries on failure (up to 3 attempts total): this is a plain read (no
        wallet debit, no order placed), so retrying can't double-charge
        anything, and Nellobytes has been observed to return a transient
        INVALID_CREDENTIALS-shaped failure — confirmed 2026-08-30, live
        account, same UserID/APIKey succeeded when re-run seconds later. A
        single immediate retry (2026-08-30's first fix) wasn't always enough
        on its own — seen recurring 2026-09-02 — so this now waits between
        attempts rather than retrying instantly.
        """
        import time

        user_id, api_key = cls._credentials()
        params = {"UserID": user_id, "APIKey": api_key}

        last_error = None
        attempts = 1 + len(cls.WALLET_BALANCE_RETRY_DELAYS)
        for attempt in range(attempts):
            if attempt > 0:
                time.sleep(cls.WALLET_BALANCE_RETRY_DELAYS[attempt - 1])

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
                "Nellobytes wallet balance check failed (attempt %s/%s): %s",
                attempt + 1, attempts, body,
            )

        logger.error("Nellobytes wallet balance check failed after %s attempts: %s", attempts, last_error)
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
        """Legacy shim: SUCCESSFUL / FAILED / PENDING. See adapters.nellobytes.normalize_order_status."""
        from vtu.gateway.adapters.nellobytes import normalize_order_status
        from vtu.gateway.types import OrderStatus

        status = normalize_order_status(orderstatus, statuscode)
        return status if status in (OrderStatus.SUCCESSFUL, OrderStatus.FAILED) else "PENDING"

    @staticmethod
    def apply_order_outcome(transaction_id, outcome):
        """Legacy shim: the single race-safe implementation lives in the gateway engine."""
        from vtu.gateway.engine import apply_outcome

        apply_outcome(transaction_id, outcome, source="legacy")
