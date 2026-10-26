"""Midtrans Snap client for SaaS wallet top-ups (platform merchant account).

Network calls never run while a wallet/top-up row lock is held. The server
key is only used for Basic auth and signature checks; it is never logged.
Notifications are verified by SHA-512 signature and then re-read from the
Midtrans status API, which is the single source of truth for settlement.
"""
import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 15
ORDER_PREFIX = "TOP-"


class GatewayError(Exception):
    """Midtrans unreachable or rejected the request (message is user-safe)."""


def configured():
    return bool(settings.MIDTRANS_SERVER_KEY.strip())


def _snap_url():
    return "https://app.midtrans.com/snap/v1/transactions" if settings.MIDTRANS_IS_PRODUCTION else "https://app.sandbox.midtrans.com/snap/v1/transactions"


def _api_base():
    return "https://api.midtrans.com" if settings.MIDTRANS_IS_PRODUCTION else "https://api.sandbox.midtrans.com"


def _request(method, url, payload=None):
    """Returns (status_code, parsed JSON). Separate function so tests can stub it."""
    auth = base64.b64encode(f"{settings.MIDTRANS_SERVER_KEY.strip()}:".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Basic {auth}",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed Midtrans hosts
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"{}")
        except ValueError:
            body = {}
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("midtrans_unreachable", extra={"error": type(exc).__name__})
        raise GatewayError("Midtrans tidak dapat dihubungi. Coba lagi beberapa saat.") from None


def order_id(topup_id):
    return f"{ORDER_PREFIX}{topup_id}"


def create_snap(*, topup_id, amount_idr, customer_name, customer_email, finish_url):
    """Create a Snap transaction; returns {"token", "redirect_url"}."""
    status, body = _request("POST", _snap_url(), {
        "transaction_details": {"order_id": order_id(topup_id), "gross_amount": amount_idr},
        "item_details": [{"id": "saas-wallet-topup", "price": amount_idr, "quantity": 1, "name": "Top-up SaaS Wallet Umrovia"}],
        "customer_details": {"first_name": (customer_name or customer_email)[:50], "email": customer_email},
        "callbacks": {"finish": finish_url},
    })
    if status not in (200, 201) or not body.get("token") or not body.get("redirect_url"):
        logger.warning("midtrans_snap_rejected", extra={"status": status, "messages": body.get("error_messages")})
        raise GatewayError("Midtrans menolak permintaan pembayaran. Periksa nominal atau coba lagi.")
    return {"token": body["token"], "redirect_url": body["redirect_url"]}


def fetch_status(order):
    """Authoritative status from Midtrans. None when the order has no transaction yet."""
    status, body = _request("GET", f"{_api_base()}/v2/{order}/status")
    code = str(body.get("status_code", status))
    if status == 404 or code == "404":
        return None
    if status != 200 or body.get("order_id") != order:
        logger.warning("midtrans_status_failed", extra={"status": status, "status_code": code})
        raise GatewayError("Status pembayaran Midtrans belum dapat diperiksa.")
    return body


def valid_signature(notification):
    """signature_key = SHA512(order_id + status_code + gross_amount + server_key)."""
    fields = [notification.get(key) for key in ("order_id", "status_code", "gross_amount", "signature_key")]
    if not all(isinstance(value, str) and value for value in fields) or not configured():
        return False
    order, status_code, gross, signature = fields
    expected = hashlib.sha512(f"{order}{status_code}{gross}{settings.MIDTRANS_SERVER_KEY.strip()}".encode()).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


def gross_idr(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return int(amount) if amount == amount.to_integral_value() else None


def outcome(status):
    """Map Midtrans status → PAID / PENDING / FAILED / REFUNDED / UNKNOWN."""
    transaction = status.get("transaction_status")
    fraud = status.get("fraud_status")
    if transaction == "settlement" or (transaction == "capture" and fraud in (None, "accept")):
        return "PAID"
    if transaction in ("pending", "authorize") or (transaction == "capture" and fraud == "challenge"):
        return "PENDING"
    if transaction in ("deny", "cancel", "expire", "failure"):
        return "FAILED"
    if transaction in ("refund", "partial_refund", "chargeback", "partial_chargeback"):
        return "REFUNDED"
    return "UNKNOWN"
