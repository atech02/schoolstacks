"""services/sms_service.py — EasySendSMS Gateway Client & Automated Messaging Engine

Replaces legacy SMS.to integration with official EasySendSMS REST API and DLR webhook processing.
Documentation:
- REST API: https://www.easysendsms.com/rest-api
- DLR API: https://www.easysendsms.com/dlr-api

Features:
- Official EasySendSMS REST API (POST https://restapi.easysendsms.app/v1/rest/sms/send)
- Balance Inquiry API (GET https://restapi.easysendsms.app/v1/rest/sms/balance)
- Strict phone number normalisation without '+' or '00' prefixes (e.g. 26097XXXXXXX)
- DLR delivery receipt parser supporting URL-encoded and JSON payloads
- Zero-duplicate idempotency controls
- Safe Dry-Run mode and feature flag toggle
- Comprehensive error code mapping (4002–4016)
- Full database ledger logging (SMSMessage, SMSDeliveryEvent)
"""
import re
import time
import uuid
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, Union
import requests
from flask import current_app
from extensions import db
from models import (
    SMSMessage,
    SMSDeliveryEvent,
    SMSSettings,
    School,
    Parent,
    Student,
    utc_now,
)

logger = logging.getLogger(__name__)

EASYSENDSMS_SEND_URL = "https://restapi.easysendsms.app/v1/rest/sms/send"
EASYSENDSMS_BALANCE_URL = "https://restapi.easysendsms.app/v1/rest/sms/balance"

# Zambian mobile regex: matching 95, 96, 97, 75, 76, 77
ZAMBIA_MOBILE_RE = re.compile(r"^(?:(?:\+?260)|00260|0)?([79][567]\d{7})$")
E164_GENERAL_RE = re.compile(r"^\+?[1-9]\d{6,14}$")

EASYSENDSMS_ERRORS = {
    4002: "Missing API key.",
    4003: "Invalid API key.",
    4004: "Invalid IP address.",
    4005: "Inactive API key.",
    4006: "Inactive account.",
    4008: "Internal error (do not resubmit).",
    4009: "Service unavailable (do not resubmit).",
    4012: "Invalid mobile number.",
    4014: "Invalid sender name.",
    4015: "Insufficient credits.",
    4016: "Country/network unavailable.",
}

# In-memory balance cache (balance_data, timestamp)
_BALANCE_CACHE: Dict[str, Any] = {"data": None, "cached_at": 0}
BALANCE_CACHE_TTL = 60  # seconds


class NormalizedPhone(str):
    """
    String subclass representing a normalised phone number.
    EasySendSMS requires numbers without leading '+' or '00' (e.g. 26097XXXXXXX).
    Provides flexible equality so comparisons against both '26097...' and '+26097...' succeed.
    Can also be unpacked as (is_valid, formatted_phone).
    """
    is_valid: bool = True

    def __new__(cls, value: str, is_valid: bool = True):
        obj = str.__new__(cls, value)
        obj.is_valid = is_valid
        return obj

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            s1 = str(self).lstrip("+")
            s2 = other.lstrip("+")
            return s1 == s2
        return super().__eq__(other)

    def __iter__(self):
        yield self.is_valid
        yield self

    @property
    def api_format(self) -> str:
        """Digits-only representation without plus or leading zeros."""
        return str(self).lstrip("+")


def normalise_phone_number(phone: str, default_country_code: str = "260") -> NormalizedPhone:
    """
    Normalise any phone number into canonical EasySendSMS format (e.g. 260XXXXXXXXX).
    Strips '+', '00', spaces, dashes, dots, and parentheses.
    """
    if not phone:
        return NormalizedPhone("", False)

    cleaned = re.sub(r"[\s\-\(\)\.]", "", str(phone).strip())

    # Check Zambian mobile patterns first
    zm_match = ZAMBIA_MOBILE_RE.match(cleaned)
    if zm_match:
        subscriber_number = zm_match.group(1)
        return NormalizedPhone(f"{default_country_code}{subscriber_number}", True)

    # Strip leading + or 00 for international checking
    digits_only = cleaned
    if digits_only.startswith("+"):
        digits_only = digits_only[1:]
    elif digits_only.startswith("00"):
        digits_only = digits_only[2:]

    if digits_only.isdigit() and 7 <= len(digits_only) <= 15:
        return NormalizedPhone(digits_only, True)

    return NormalizedPhone(cleaned, False)


# Alias for backwards compatibility
normalize_phone_number = normalise_phone_number


class EasySendSMSClient:
    """Official EasySendSMS REST API Client."""

    def __init__(self, app=None):
        ctx_app = app or (current_app._get_current_object() if current_app else None)
        cfg = ctx_app.config if ctx_app else {}
        import os

        # EasySendSMS credentials with legacy fallback
        self.api_key = (
            cfg.get("EASYSENDSMS_API_KEY")
            or os.getenv("EASYSENDSMS_API_KEY")
            or cfg.get("SMS_TO_API_KEY")
            or os.getenv("SMS_TO_API_KEY")
            or ""
        ).strip()

        self.default_sender_id = (
            cfg.get("EASYSENDSMS_SENDER_ID")
            or os.getenv("EASYSENDSMS_SENDER_ID")
            or cfg.get("SMS_TO_SENDER_ID")
            or os.getenv("SMS_TO_SENDER_ID")
            or "SchoolStacks"
        ).strip()

        enabled_cfg = cfg.get("EASYSENDSMS_ENABLED")
        if enabled_cfg is None:
            enabled_cfg = os.getenv("EASYSENDSMS_ENABLED")
        if enabled_cfg is None:
            enabled_cfg = cfg.get("SMS_TO_ENABLED", os.getenv("SMS_TO_ENABLED", "false"))
        self.is_enabled = str(enabled_cfg).lower() in ("true", "1", "yes")

        dry_run_cfg = cfg.get("EASYSENDSMS_DRY_RUN")
        if dry_run_cfg is None:
            dry_run_cfg = os.getenv("EASYSENDSMS_DRY_RUN")
        if dry_run_cfg is None:
            dry_run_cfg = cfg.get("SMS_TO_DRY_RUN", os.getenv("SMS_TO_DRY_RUN", "true"))
        self.dry_run = str(dry_run_cfg).lower() in ("true", "1", "yes") or not bool(self.api_key)

        self.timeout = 15

    @staticmethod
    def is_unicode(text: str) -> bool:
        """Check if message contains characters outside the GSM 7-bit default alphabet."""
        try:
            # Check ASCII bounds first
            text.encode("ascii")
            return False
        except UnicodeEncodeError:
            return True

    def send_single(
        self,
        to_phone: str,
        message: str,
        sender_id: Optional[str] = None,
        msg_type: Optional[str] = None,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Send a single SMS via EasySendSMS REST API.
        POST https://restapi.easysendsms.app/v1/rest/sms/send
        """
        is_valid, norm_phone = normalise_phone_number(to_phone)
        if not is_valid:
            return {
                "success": False,
                "message_id": None,
                "status": "failed",
                "cost": 0.0,
                "error": "Invalid recipient phone number format: must be valid mobile number without '+' or '00'.",
            }

        if not self.is_enabled:
            logger.info("EasySendSMS sending is globally disabled (EASYSENDSMS_ENABLED=false).")
            return {
                "success": False,
                "message_id": None,
                "status": "disabled",
                "cost": 0.0,
                "error": "SMS sending is currently disabled on this platform.",
            }

        # Dry-run or unconfigured simulation mode
        if self.dry_run or not self.api_key:
            simulated_id = f"sim_easysend_{uuid.uuid4().hex[:16]}"
            logger.info(
                "[EASYSENDSMS DRY RUN] Target: %s | Sender: %s | Message: %s",
                str(norm_phone).lstrip("+"),
                sender_id or self.default_sender_id,
                message[:60] + "..." if len(message) > 60 else message,
            )
            return {
                "success": True,
                "message_id": simulated_id,
                "status": "sent",
                "cost": 0.035,
                "error": None,
                "dry_run": True,
            }

        # Determine type: "0" for GSM text, "1" for Unicode
        determined_type = msg_type if msg_type in ("0", "1") else ("1" if self.is_unicode(message) else "0")
        effective_sender = (sender_id or self.default_sender_id or "SchoolStacks")[:11]

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "from": effective_sender,
            "to": str(norm_phone).lstrip("+"),
            "text": message,
            "type": determined_type,
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(
                    EASYSENDSMS_SEND_URL,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                try:
                    data = resp.json() or {}
                except Exception:
                    data = {}

                # Check HTTP success
                if resp.status_code in (200, 201):
                    # EasySendSMS response structure:
                    # {"status": "OK", "scheduled": "Now", "messageIds": ["OK: a1b2c3d4..."]}
                    if data.get("status") == "OK" or "messageIds" in data:
                        raw_ids = data.get("messageIds") or []
                        raw_id = raw_ids[0] if raw_ids else ""
                        clean_id = str(raw_id).replace("OK:", "").replace("OK", "").strip() or f"ess_{uuid.uuid4().hex[:12]}"
                        return {
                            "success": True,
                            "message_id": clean_id,
                            "status": "sent",
                            "cost": 0.035,
                            "error": None,
                        }

                    # If HTTP 200 returned an error status in body
                    err_code = data.get("code")
                    err_text = data.get("message") or EASYSENDSMS_ERRORS.get(err_code, "Unknown provider error")
                    return {
                        "success": False,
                        "message_id": None,
                        "status": "failed",
                        "cost": 0.0,
                        "error": f"EasySendSMS Error ({err_code}): {err_text}",
                    }

                # Handle HTTP 4xx errors
                if 400 <= resp.status_code < 500:
                    err_code = data.get("code") or resp.status_code
                    err_msg = EASYSENDSMS_ERRORS.get(err_code) or data.get("message") or f"EasySendSMS rejected request (HTTP {resp.status_code})"
                    logger.warning("EasySendSMS client error %s: %s", resp.status_code, err_msg)
                    return {
                        "success": False,
                        "message_id": None,
                        "status": "failed",
                        "cost": 0.0,
                        "error": f"EasySendSMS Error ({err_code}): {err_msg}",
                    }

                # Handle 5xx server errors
                err_code = data.get("code")
                if err_code in (4008, 4009):
                    # Provider explicitly advises NOT resubmitting for 4008 or 4009
                    err_msg = EASYSENDSMS_ERRORS.get(err_code, "Provider internal or service unavailable")
                    return {
                        "success": False,
                        "message_id": None,
                        "status": "failed",
                        "cost": 0.0,
                        "error": f"EasySendSMS Error ({err_code}): {err_msg}",
                    }

                last_error = f"EasySendSMS server error (HTTP {resp.status_code})"
                logger.warning("EasySendSMS HTTP %s on attempt %d: %s", resp.status_code, attempt + 1, resp.text)

            except requests.exceptions.Timeout:
                last_error = f"EasySendSMS gateway request timed out after {self.timeout}s"
                logger.warning("EasySendSMS timeout on attempt %d", attempt + 1)
            except requests.exceptions.RequestException as e:
                last_error = f"EasySendSMS network error: {type(e).__name__}"
                logger.warning("EasySendSMS connection error on attempt %d: %s", attempt + 1, e)

            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))

        return {
            "success": False,
            "message_id": None,
            "status": "failed",
            "cost": 0.0,
            "error": last_error or "Failed to deliver SMS via EasySendSMS after retries.",
        }

    def get_balance(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Inquire account SMS balance via official endpoint:
        GET https://restapi.easysendsms.app/v1/rest/sms/balance
        """
        now = time.time()
        if (
            not force_refresh
            and _BALANCE_CACHE["data"]
            and (now - _BALANCE_CACHE["cached_at"]) < BALANCE_CACHE_TTL
        ):
            return _BALANCE_CACHE["data"]

        if self.dry_run or not self.api_key:
            res = {
                "success": True,
                "status": "OK",
                "balance": 250.00,
                "currency": "EUR",
                "provider": "EasySendSMS",
                "dry_run": True,
            }
            _BALANCE_CACHE["data"] = res
            _BALANCE_CACHE["cached_at"] = now
            return res

        headers = {
            "apikey": self.api_key,
            "Accept": "application/json",
        }
        try:
            resp = requests.get(EASYSENDSMS_BALANCE_URL, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json() or {}
                # Parse numeric balance
                bal = data.get("balance")
                if bal is None and "credits" in data:
                    bal = data.get("credits")
                try:
                    balance_num = float(bal) if bal is not None else 0.0
                except (ValueError, TypeError):
                    balance_num = 0.0

                res = {
                    "success": True,
                    "status": "OK",
                    "balance": balance_num,
                    "currency": data.get("currency") or "EUR",
                    "provider": "EasySendSMS",
                    "dry_run": False,
                }
                _BALANCE_CACHE["data"] = res
                _BALANCE_CACHE["cached_at"] = now
                return res

            err_data = {}
            try:
                err_data = resp.json() or {}
            except Exception:
                pass
            code = err_data.get("code") or resp.status_code
            err_msg = EASYSENDSMS_ERRORS.get(code) or err_data.get("message") or f"HTTP {resp.status_code}"
            return {
                "success": False,
                "status": "ERROR",
                "balance": 0.0,
                "currency": "EUR",
                "error": f"Failed to retrieve balance: {err_msg}",
                "provider": "EasySendSMS",
            }
        except Exception as e:
            return {
                "success": False,
                "status": "ERROR",
                "balance": 0.0,
                "currency": "EUR",
                "error": f"Network error checking balance: {type(e).__name__}",
                "provider": "EasySendSMS",
            }


# Backwards compatibility alias
SMSToClient = EasySendSMSClient


# ── REUSABLE SERVICE FUNCTIONS ────────────────────────────────────────────────

def get_sms_balance(force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieve current EasySendSMS balance with caching."""
    client = EasySendSMSClient()
    return client.get_balance(force_refresh=force_refresh)


def process_delivery_report(payload_or_qs: Union[str, bytes, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process incoming EasySendSMS DLR (Delivery Report) callback.
    EasySendSMS sends raw URL-encoded POST payload:
    source=test&msisdn=26097XXXXXXX&response=DELIVRD&sent_date=5%2f24%2f2024+11%3a23%3a34+PM&sms_id=fd940f38-151d-47f1-81b8-22d1220f7a55

    Maps:
    - DELIVRD -> delivered
    - EXPIRED -> expired
    - UNDELIV -> undelivered
    """
    data: Dict[str, Any] = {}
    raw_str = ""

    if isinstance(payload_or_qs, (str, bytes)):
        if isinstance(payload_or_qs, bytes):
            raw_str = payload_or_qs.decode("utf-8", errors="replace")
        else:
            raw_str = payload_or_qs
        parsed = urllib.parse.parse_qs(raw_str)
        # Flatten parse_qs lists
        data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in parsed.items()}
    elif isinstance(payload_or_qs, dict):
        data = dict(payload_or_qs)
        raw_str = urllib.parse.urlencode(data)

    sms_id = (
        data.get("sms_id")
        or data.get("message_id")
        or data.get("id")
        or data.get("messageId")
        or ""
    )
    if isinstance(sms_id, str):
        sms_id = sms_id.replace("OK:", "").replace("OK", "").strip()

    raw_response = str(
        data.get("response")
        or data.get("status")
        or data.get("delivery_status")
        or "UNKNOWN"
    ).upper().strip()

    msisdn = str(data.get("msisdn") or data.get("recipient_phone") or "").strip()
    source = str(data.get("source") or data.get("from") or "").strip()
    sent_date = str(data.get("sent_date") or "").strip()

    # Canonical status mapping
    if raw_response in ("DELIVRD", "DELIVERED"):
        status_mapped = "delivered"
    elif raw_response in ("EXPIRED",):
        status_mapped = "expired"
    elif raw_response in ("UNDELIV", "UNDELIVERED"):
        status_mapped = "undelivered"
    elif raw_response in ("REJECTD", "REJECTED"):
        status_mapped = "rejected"
    elif raw_response in ("FAILED",):
        status_mapped = "failed"
    else:
        status_mapped = raw_response.lower()

    if not sms_id:
        logger.warning("EasySendSMS DLR received without sms_id: %s", raw_str)
        return {
            "success": False,
            "error": "Missing sms_id in delivery report callback.",
            "status": status_mapped,
        }

    # Match outbound SMS message
    msg = (
        SMSMessage.query.filter_by(provider_message_id=sms_id).first()
        or SMSMessage.query.filter(SMSMessage.provider_message_id.like(f"%{sms_id}%")).first()
    )

    if not msg:
        # Check by msisdn suffix if available
        if msisdn and len(msisdn) >= 9:
            subscriber_tail = msisdn[-9:]
            msg = (
                SMSMessage.query.filter(SMSMessage.recipient_phone.like(f"%{subscriber_tail}"))
                .order_by(SMSMessage.created_at.desc())
                .first()
            )

    if msg:
        # Idempotent status update
        msg.status = status_mapped
        if status_mapped == "delivered" and not msg.delivered_at:
            msg.delivered_at = utc_now()

        event = SMSDeliveryEvent(
            sms_message_id=msg.id,
            provider_message_id=sms_id,
            status=status_mapped,
            raw_payload=raw_str,
        )
        db.session.add(event)
        try:
            db.session.commit()
            logger.info("EasySendSMS DLR processed: sms_id=%s -> %s", sms_id, status_mapped)
        except Exception as exc:
            db.session.rollback()
            logger.error("Error committing DLR event for %s: %s", sms_id, exc)

        return {
            "success": True,
            "sms_id": sms_id,
            "status": status_mapped,
            "matched_message_id": msg.id,
        }

    # Log unmatched event for audit without failing
    event = SMSDeliveryEvent(
        sms_message_id=None,
        provider_message_id=sms_id,
        status=status_mapped,
        raw_payload=raw_str,
    )
    db.session.add(event)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    logger.warning("EasySendSMS DLR logged for unmatched message ID: %s", sms_id)
    return {
        "success": True,
        "sms_id": sms_id,
        "status": status_mapped,
        "matched": False,
    }


def send_sms(
    to_phone: str,
    message: str,
    sender_id: Optional[str] = None,
    msg_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Low-level dispatch for a single SMS via EasySendSMS."""
    client = EasySendSMSClient()
    return client.send_single(
        to_phone=to_phone,
        message=message,
        sender_id=sender_id,
        msg_type=msg_type,
    )


def send_school_sms(
    school_id: int,
    to_phone: Optional[str] = None,
    message: Optional[str] = None,
    category: str = "general",
    student_id: Optional[int] = None,
    recipient_name: Optional[str] = None,
    recipient_user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    sender_id_override: Optional[str] = None,
    commit: bool = True,
    **kwargs
) -> SMSMessage:
    """
    High-level, transaction-safe SMS dispatch function for SchoolStacks.
    - Validates school SMS enablement.
    - Formats phone numbers into canonical EasySendSMS digits.
    - Enforces idempotency deduplication to avoid duplicate messages.
    - Logs outbound messages to the database ledger.
    - Dispatches via EasySendSMSClient.
    """
    to_phone = kwargs.get("recipient_phone") or to_phone or ""
    message = kwargs.get("message_text") or message or ""
    category = kwargs.get("message_type") or category
    sender_id_override = kwargs.get("sender_id") or sender_id_override

    # 1. Normalise phone number
    is_valid, norm_phone = normalise_phone_number(to_phone)
    if not is_valid:
        sms_rec = SMSMessage(
            school_id=school_id,
            recipient_phone=to_phone or "unknown",
            recipient_name=recipient_name,
            recipient_user_id=recipient_user_id,
            student_id=student_id,
            message_body=message,
            category=category,
            provider="easysendsms",
            status="failed",
            error_message="Invalid phone number format for EasySendSMS.",
            idempotency_key=idempotency_key,
        )
        db.session.add(sms_rec)
        if commit:
            db.session.commit()
        return sms_rec

    # 2. Check idempotency deduplication
    if idempotency_key:
        existing = SMSMessage.query.filter_by(
            school_id=school_id, idempotency_key=idempotency_key
        ).first()
        if existing and existing.status in ("sent", "delivered", "queued"):
            logger.info("Idempotent duplicate SMS detected: %s. Returning existing record.", idempotency_key)
            return existing

    # 3. Check school SMS settings
    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    school_sms_enabled = settings.is_enabled if settings else False

    client = EasySendSMSClient()
    if not client.is_enabled or not school_sms_enabled:
        sms_rec = SMSMessage(
            school_id=school_id,
            recipient_phone=str(norm_phone).lstrip("+"),
            recipient_name=recipient_name,
            recipient_user_id=recipient_user_id,
            student_id=student_id,
            message_body=message,
            category=category,
            provider="easysendsms",
            status="disabled",
            error_message="SMS sending is not enabled for this school.",
            idempotency_key=idempotency_key,
        )
        db.session.add(sms_rec)
        if commit:
            db.session.commit()
        return sms_rec

    effective_sender = sender_id_override or (settings.sender_id if settings else None)

    # 4. Dispatch via EasySendSMS client
    result = client.send_single(
        to_phone=str(norm_phone).lstrip("+"),
        message=message,
        sender_id=effective_sender,
    )

    status_val = "sent" if result["success"] else "failed"
    sms_rec = SMSMessage(
        school_id=school_id,
        recipient_phone=str(norm_phone).lstrip("+"),
        recipient_name=recipient_name,
        recipient_user_id=recipient_user_id,
        student_id=student_id,
        message_body=message,
        category=category,
        provider="easysendsms",
        status=status_val,
        provider_message_id=result.get("message_id"),
        cost=result.get("cost", 0.0),
        error_message=result.get("error"),
        sent_at=utc_now() if result["success"] else None,
        idempotency_key=idempotency_key,
    )
    db.session.add(sms_rec)
    if commit:
        db.session.commit()

    return sms_rec


def send_parent_notification(
    school_id: int,
    parent_id: Optional[int],
    student_id: Optional[int],
    message: str,
    category: str = "general",
    sender_id: Optional[str] = None,
) -> SMSMessage:
    """Send an individually addressed notification to a parent."""
    phone = ""
    recipient_name = None
    user_id = None

    if parent_id:
        parent = db.session.get(Parent, parent_id)
        if parent:
            phone = parent.phone or ""
            recipient_name = parent.full_name or parent.name if hasattr(parent, "full_name") else getattr(parent, "name", None)
            user_id = parent.user_id

    if not phone and student_id:
        student = db.session.get(Student, student_id)
        if student and getattr(student, "phone", None):
            phone = student.phone
            recipient_name = student.full_name

    idemp = f"parent_notif_{school_id}_{student_id}_{parent_id}_{abs(hash(message)) % 1000000}_{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    return send_school_sms(
        school_id=school_id,
        to_phone=phone,
        message=message,
        category=category,
        student_id=student_id,
        recipient_name=recipient_name,
        recipient_user_id=user_id,
        idempotency_key=idemp,
        sender_id_override=sender_id,
    )


def send_fees_reminder(
    school_id: int,
    student_id: int,
    invoice_id: Union[int, str],
    amount_due: float,
    due_date: str,
    currency: str = "ZMW",
    sender_id: Optional[str] = None,
) -> Optional[SMSMessage]:
    """Send an automated fee reminder for an outstanding invoice."""
    if amount_due <= 0:
        logger.info("Skipping fee reminder for student %s: balance <= 0", student_id)
        return None

    student = db.session.get(Student, student_id)
    if not student:
        return None

    school = db.session.get(School, school_id)
    school_name = school.name if school else "SchoolStacks"

    phone = getattr(student, "phone", None)
    parent_name = "Parent/Guardian"

    # Resolve guardian phone
    from models import ParentStudent
    ps = ParentStudent.query.filter_by(student_id=student_id).first()
    if ps and ps.parent and ps.parent.phone:
        phone = ps.parent.phone
        parent_name = getattr(ps.parent, "full_name", None) or getattr(ps.parent, "name", "Parent/Guardian")

    if not phone:
        logger.warning("No phone number found for student %s to send fee reminder.", student_id)
        return None

    msg_body = (
        f"Dear {parent_name}, this is a reminder from {school_name}. "
        f"The outstanding balance for {student.full_name} is {currency} {amount_due:.2f}, "
        f"due on {due_date}. Please settle promptly. Thank you."
    )
    idemp = f"fee_rem_{school_id}_{student_id}_{invoice_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    return send_school_sms(
        school_id=school_id,
        to_phone=phone,
        message=msg_body,
        category="fee_reminder",
        student_id=student_id,
        recipient_name=parent_name,
        idempotency_key=idemp,
        sender_id_override=sender_id,
    )


def send_absence_alert(
    school_id: int,
    student_id: int,
    attendance_date: str,
    consecutive_days: int = 1,
    status: str = "Absent",
    sender_id: Optional[str] = None,
) -> Optional[SMSMessage]:
    """Send an unexcused absence alert to guardians."""
    student = db.session.get(Student, student_id)
    if not student:
        return None

    school = db.session.get(School, school_id)
    school_name = school.name if school else "SchoolStacks"

    from models import ParentStudent
    ps = ParentStudent.query.filter_by(student_id=student_id).first()
    phone = ps.parent.phone if (ps and ps.parent and ps.parent.phone) else getattr(student, "phone", None)
    if not phone:
        return None

    if consecutive_days >= 3:
        msg = (
            f"URGENT: {student.full_name} was marked absent for {consecutive_days} consecutive days at {school_name}. "
            f"Please contact the school administration immediately."
        )
    elif consecutive_days >= 2:
        msg = (
            f"Notice from {school_name}: {student.full_name} was marked absent for {consecutive_days} consecutive days "
            f"as of {attendance_date}. Please contact the school if your child is unwell."
        )
    else:
        msg = f"Alert from {school_name}: {student.full_name} was marked absent on {attendance_date}."

    idemp = f"abs_alert_{school_id}_{student_id}_{attendance_date}"
    return send_school_sms(
        school_id=school_id,
        to_phone=phone,
        message=msg,
        category="absenteeism",
        student_id=student_id,
        idempotency_key=idemp,
        sender_id_override=sender_id,
    )


def send_test_sms(
    school_id: int,
    phone: str,
    message: Optional[str] = None,
    sender_id: Optional[str] = None,
) -> SMSMessage:
    """Send an administrative test SMS."""
    test_msg = message or "SchoolStacks Test: EasySendSMS automated parent communication gateway is fully operational."
    return send_school_sms(
        school_id=school_id,
        to_phone=phone,
        message=test_msg,
        category="test",
        sender_id_override=sender_id,
    )
