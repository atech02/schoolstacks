"""
services/lipila.py — Lipila Payment Gateway Client (Zambia)
Supports Mobile Money (MTN MoMo, Airtel Money, Zamtel Kwacha) and Card Collections,
Transaction Status Reconciliation, Webhook Verification, and a strictly guarded
Development/Testing Sandbox Simulator.
"""
import hmac
import hashlib
import logging
import re
import secrets
from datetime import datetime, timezone
import requests
from flask import current_app, url_for

logger = logging.getLogger(__name__)

ZAMBIA_PHONE_RE = re.compile(r"^(?:260|0)?(9[567]\d{7}|7[567]\d{7})$")


def normalize_zambia_phone(phone: str) -> str:
    """Normalize a Zambian mobile number to international format 260XXXXXXXXX."""
    if not phone:
        return ""
    cleaned = re.sub(r"[\s\-\+\(\)]", "", str(phone))
    m = ZAMBIA_PHONE_RE.match(cleaned)
    if not m:
        return ""
    return f"260{m.group(1)}"


class LipilaError(Exception):
    """Operational error communicating with Lipila API."""


class LipilaClient:
    """Client for Lipila Collections API (v1)."""

    def __init__(self, app=None):
        cfg = (app or current_app).config
        self.env = cfg.get("LIPILA_ENV", "sandbox").lower()
        self.is_production = bool(cfg.get("IS_PRODUCTION", False))
        self.api_key = cfg.get("LIPILA_API_KEY", "").strip()
        self.webhook_secret = cfg.get("LIPILA_WEBHOOK_SECRET", "").strip()
        self.currency = cfg.get("LIPILA_CURRENCY", "ZMW")
        self.base_url = (
            cfg.get("LIPILA_LIVE_URL", "https://api.lipila.io/api/v1")
            if self.env == "production" or self.is_production
            else cfg.get("LIPILA_SANDBOX_URL", "https://api.lipila.dev/api/v1")
        ).rstrip("/")
        self.simulator_enabled = (
            not self.is_production
            and self.env != "production"
            and bool(cfg.get("LIPILA_SIMULATOR_ENABLED", False))
        )
        self.timeout = 20

    @staticmethod
    def generate_reference(prefix: str = "LPL") -> str:
        """Generate a unique, collision-resistant transaction reference."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        rand = secrets.token_hex(4).upper()
        return f"{prefix}-{ts}-{rand}"

    def _headers(self, callback_url: str = None) -> dict:
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        }
        if callback_url:
            headers["callbackUrl"] = callback_url
        return headers

    def initiate_mobile_money_collection(
        self,
        *,
        reference_id: str,
        amount: float,
        phone_number: str,
        narration: str,
        email: str = "",
        callback_url: str = "",
    ) -> dict:
        """
        Initiate a Lipila Mobile Money collection (MTN, Airtel, Zamtel).
        Returns normalized dict:
          {
            "reference_id": str,
            "transaction_id": str | None,
            "status": "pending" | "failed",
            "is_simulated": bool,
            "redirect_url": str | None,
            "message": str,
          }
        """
        normalized_phone = normalize_zambia_phone(phone_number)
        if not normalized_phone:
            raise LipilaError("Enter a valid Zambian mobile money number (e.g. 097..., 096..., 095...).")

        if amount <= 0:
            raise LipilaError("Payment amount must be greater than zero.")

        # Development/Test Sandbox Simulator when no real API key is configured
        if self.simulator_enabled:
            logger.info(
                "Lipila Sandbox Simulator: initiated MoMo collection ref=%s amount=%.2f %s",
                reference_id,
                amount,
                self.currency,
            )
            return {
                "reference_id": reference_id,
                "transaction_id": f"SIM-MOMO-{secrets.token_hex(4).upper()}",
                "status": "pending",
                "is_simulated": True,
                "redirect_url": url_for("billing.sandbox_checkout", reference_id=reference_id),
                "message": "TEST MODE: Simulated Mobile Money prompt created.",
            }

        if not self.api_key:
            raise LipilaError("Lipila API key is not configured.")

        payload = {
            "referenceId": reference_id,
            "amount": round(float(amount), 2),
            "narration": narration[:120],
            "accountNumber": normalized_phone,
            "currency": self.currency,
            "email": email or "payments@edumanage.zm",
        }

        try:
            resp = requests.post(
                f"{self.base_url}/collections/mobile-money",
                json=payload,
                headers=self._headers(callback_url),
                timeout=self.timeout,
            )
            data = resp.json() if resp.content else {}
        except requests.Timeout as exc:
            logger.error("Lipila MoMo collection timeout ref=%s", reference_id)
            raise LipilaError("Payment gateway request timed out. Please check payment status shortly.") from exc
        except requests.RequestException as exc:
            logger.error("Lipila MoMo collection request failed ref=%s: %s", reference_id, type(exc).__name__)
            raise LipilaError("Unable to reach payment gateway. Please try again.") from exc
        except ValueError as exc:
            logger.error("Lipila MoMo collection non-JSON response ref=%s status=%s", reference_id, resp.status_code)
            raise LipilaError("Unexpected response from payment gateway.") from exc

        if resp.status_code not in (200, 201, 202):
            err_msg = data.get("message") or data.get("error") or "Mobile money request rejected."
            logger.warning("Lipila MoMo error ref=%s code=%s msg=%s", reference_id, resp.status_code, err_msg)
            raise LipilaError(err_msg)

        tx_id = data.get("transactionId") or data.get("id") or reference_id
        raw_status = str(data.get("status", "pending")).lower()
        norm_status = self._normalize_status(raw_status)

        return {
            "reference_id": reference_id,
            "transaction_id": tx_id,
            "status": norm_status,
            "is_simulated": False,
            "redirect_url": None,
            "message": data.get("message", "A Mobile Money PIN prompt has been sent to your phone."),
        }

    def initiate_card_collection(
        self,
        *,
        reference_id: str,
        amount: float,
        customer_info: dict,
        narration: str,
        back_url: str,
        callback_url: str = "",
        reference_data: str = "",
    ) -> dict:
        """
        Initiate a Lipila Hosted Card Collection (`POST /collections/card`).
        Never collects or stores card numbers/CVVs on our server.
        """
        if amount <= 0:
            raise LipilaError("Payment amount must be greater than zero.")

        if self.simulator_enabled:
            logger.info(
                "Lipila Sandbox Simulator: initiated Card collection ref=%s amount=%.2f %s",
                reference_id,
                amount,
                self.currency,
            )
            return {
                "reference_id": reference_id,
                "transaction_id": f"SIM-CARD-{secrets.token_hex(4).upper()}",
                "status": "pending",
                "is_simulated": True,
                "redirect_url": url_for("billing.sandbox_checkout", reference_id=reference_id),
                "message": "TEST MODE: Redirecting to Sandbox Card Simulator.",
            }

        if not self.api_key:
            raise LipilaError("Lipila API key is not configured.")

        phone = normalize_zambia_phone(customer_info.get("phone_number", "")) or "260970000000"
        payload = {
            "customerInfo": {
                "firstName": (customer_info.get("first_name") or "School")[:50],
                "lastName": (customer_info.get("last_name") or "Customer")[:50],
                "phoneNumber": phone,
                "city": customer_info.get("city") or "Lusaka",
                "country": customer_info.get("country") or "Zambia",
                "address": customer_info.get("address") or "Lusaka, Zambia",
                "email": customer_info.get("email") or "billing@edumanage.zm",
                "zip": customer_info.get("zip") or "10101",
            },
            "collectionRequest": {
                "referenceId": reference_id,
                "amount": round(float(amount), 2),
                "narration": narration[:120],
                "accountNumber": phone,
                "currency": self.currency,
                "backUrl": back_url,
                "referenceData": reference_data,
            },
        }

        try:
            resp = requests.post(
                f"{self.base_url}/collections/card",
                json=payload,
                headers=self._headers(callback_url),
                timeout=self.timeout,
            )
            data = resp.json() if resp.content else {}
        except requests.Timeout as exc:
            logger.error("Lipila Card collection timeout ref=%s", reference_id)
            raise LipilaError("Card checkout request timed out. Please try again.") from exc
        except requests.RequestException as exc:
            logger.error("Lipila Card collection failed ref=%s: %s", reference_id, type(exc).__name__)
            raise LipilaError("Unable to connect to card payment gateway.") from exc
        except ValueError as exc:
            raise LipilaError("Unexpected response from card payment gateway.") from exc

        if resp.status_code not in (200, 201, 202):
            err_msg = data.get("message") or data.get("error") or "Card checkout request failed."
            logger.warning("Lipila Card error ref=%s code=%s msg=%s", reference_id, resp.status_code, err_msg)
            raise LipilaError(err_msg)

        redirect_url = (
            data.get("redirectUrl")
            or data.get("checkoutUrl")
            or data.get("paymentUrl")
            or data.get("url")
        )
        tx_id = data.get("transactionId") or data.get("id") or reference_id
        raw_status = str(data.get("status", "pending")).lower()

        return {
            "reference_id": reference_id,
            "transaction_id": tx_id,
            "status": self._normalize_status(raw_status),
            "is_simulated": False,
            "redirect_url": redirect_url,
            "message": data.get("message", "Redirecting to Lipila secure card checkout."),
        }

    def check_transaction_status(self, reference_id: str) -> dict:
        """
        Query Lipila `GET /collections/check-status` to verify authoritative transaction status.
        Returns:
          {
            "reference_id": str,
            "transaction_id": str | None,
            "status": "pending" | "completed" | "failed",
            "amount": float | None,
            "currency": str | None,
          }
        """
        if not reference_id:
            raise LipilaError("Missing referenceId for status check.")

        if self.simulator_enabled and not self.api_key:
            # In simulator mode without live API keys, status is stored in DB via sandbox_checkout action
            return {
                "reference_id": reference_id,
                "transaction_id": None,
                "status": "pending",
                "amount": None,
                "currency": self.currency,
                "is_simulated": True,
            }

        try:
            resp = requests.get(
                f"{self.base_url}/collections/check-status",
                params={"referenceId": reference_id},
                headers=self._headers(),
                timeout=self.timeout,
            )
            data = resp.json() if resp.content else {}
        except requests.Timeout as exc:
            logger.warning("Lipila status check timeout ref=%s", reference_id)
            raise LipilaError("Status check timed out.") from exc
        except requests.RequestException as exc:
            logger.warning("Lipila status check failed ref=%s: %s", reference_id, type(exc).__name__)
            raise LipilaError("Could not verify transaction status with Lipila.") from exc
        except ValueError as exc:
            raise LipilaError("Invalid JSON response during status check.") from exc

        if resp.status_code != 200:
            err_msg = data.get("message") or data.get("error") or "Status lookup failed."
            raise LipilaError(err_msg)

        raw_status = str(data.get("status") or data.get("transactionStatus") or "pending").lower()
        amount_val = data.get("amount")
        try:
            amount_val = float(amount_val) if amount_val is not None else None
        except (TypeError, ValueError):
            amount_val = None

        return {
            "reference_id": data.get("referenceId") or reference_id,
            "transaction_id": data.get("transactionId") or data.get("id"),
            "status": self._normalize_status(raw_status),
            "amount": amount_val,
            "currency": data.get("currency") or self.currency,
            "is_simulated": False,
        }

    def verify_webhook_request(self, raw_body: bytes, headers: dict) -> bool:
        """
        Verify webhook callback authenticity.
        Checks HMAC-SHA256 signature (`X-Lipila-Signature` / `X-Webhook-Signature`) or
        shared webhook secret (`X-Webhook-Secret` / `x-api-key`).
        In production, rejects unverified webhooks if neither webhook_secret nor api_key matches.
        """
        sig_header = (
            headers.get("X-Lipila-Signature")
            or headers.get("X-Webhook-Signature")
            or headers.get("x-lipila-signature")
            or ""
        ).strip()
        token_header = (
            headers.get("X-Webhook-Secret")
            or headers.get("x-api-key")
            or ""
        ).strip()

        secret = self.webhook_secret or self.api_key
        if not secret:
            # Only allow unsigned local webhook in simulator dev/test mode
            return self.simulator_enabled and not self.is_production

        if sig_header:
            expected_sig = hmac.new(
                secret.encode("utf-8"),
                raw_body or b"",
                hashlib.sha256,
            ).hexdigest()
            # Support optional 'sha256=' prefix
            clean_sig = sig_header.split("=", 1)[-1].strip()
            if hmac.compare_digest(clean_sig.lower(), expected_sig.lower()):
                return True

        if token_header and hmac.compare_digest(token_header, secret):
            return True

        return False

    @staticmethod
    def _normalize_status(raw_status: str) -> str:
        s = (raw_status or "").strip().lower()
        if s in ("successful", "success", "completed", "paid", "succeeded", "approved", "00"):
            return "completed"
        if s in ("failed", "declined", "rejected", "cancelled", "canceled", "expired", "error"):
            return "failed"
        return "pending"
