"""Inbound WhatsApp webhooks: signature check and the messages they carry.

Meta posts ``{"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": ...}]}]}``.
A ``value`` holds the receiving number (``metadata.phone_number_id``) and ``messages`` (or delivery ``statuses``,
which are ignored here). Parsing is lenient: a malformed message is skipped, never fails the whole delivery.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.logger import Logger
from app.ingestion.normalize import normalize_phone

logger = Logger(__name__)

SIGNATURE_PREFIX = "sha256="


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """``X-Hub-Signature-256``: HMAC-SHA256 of the raw body with the Meta app secret."""
    if not header or not header.startswith(SIGNATURE_PREFIX):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix(SIGNATURE_PREFIX))


@dataclass(frozen=True)
class WhatsAppMessage:
    """One inbound message. ``reply_id`` is the id of a tapped button (interactive reply or template button)."""

    phone_number_id: str
    message_id: str
    sender: str  # E.164
    profile_name: str | None
    sent_at: datetime
    kind: str  # the WhatsApp message type: text, interactive, button, image, ...
    text: str | None
    reply_id: str | None
    raw: dict[str, Any]


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_and_reply(message: dict[str, Any]) -> tuple[str | None, str | None]:
    kind = message.get("type")
    if kind == "text":
        return _dict(message.get("text")).get("body"), None
    if kind == "interactive":
        reply = _dict(_dict(message.get("interactive")).get("button_reply"))
        return reply.get("title"), reply.get("id")
    if kind == "button":  # a quick-reply button of a template message
        button = _dict(message.get("button"))
        return button.get("text"), button.get("payload")
    return None, None


def _sent_at(timestamp: object) -> datetime:
    try:
        return datetime.fromtimestamp(int(str(timestamp)), UTC)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(UTC)


def _message(phone_number_id: str, names: dict[str, str], message: dict[str, Any]) -> WhatsAppMessage | None:
    message_id, sender = message.get("id"), message.get("from")
    if not isinstance(message_id, str) or not isinstance(sender, str):
        return None
    try:
        phone = normalize_phone("+" + sender.lstrip("+"))
    except ValueError:
        return None
    text, reply_id = _text_and_reply(message)
    return WhatsAppMessage(
        phone_number_id=phone_number_id,
        message_id=message_id,
        sender=phone,
        profile_name=names.get(sender),
        sent_at=_sent_at(message.get("timestamp")),
        kind=str(message.get("type") or "unknown"),
        text=(text.strip() or None) if isinstance(text, str) else None,
        reply_id=reply_id if isinstance(reply_id, str) else None,
        raw=message,
    )


def parse_messages(payload: object) -> list[WhatsAppMessage]:
    """Every inbound message of a webhook delivery, in order."""
    messages: list[WhatsAppMessage] = []
    for entry in _list(_dict(payload).get("entry")):
        for change in _list(_dict(entry).get("changes")):
            change = _dict(change)
            if change.get("field") != "messages":
                continue
            value = _dict(change.get("value"))
            phone_number_id = _dict(value.get("metadata")).get("phone_number_id")
            if not isinstance(phone_number_id, str):
                continue
            names = {
                contact["wa_id"]: name
                for contact in map(_dict, _list(value.get("contacts")))
                if isinstance(contact.get("wa_id"), str)
                and isinstance(name := _dict(contact.get("profile")).get("name"), str)
            }
            for raw in _list(value.get("messages")):
                parsed = _message(phone_number_id, names, _dict(raw))
                if parsed is None:
                    logger.fire("whatsapp_message_unparsed", level="warning", phone_number_id=phone_number_id)
                else:
                    messages.append(parsed)
    return messages
