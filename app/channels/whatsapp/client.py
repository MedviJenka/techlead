"""Sends WhatsApp messages through the Cloud API (``POST /{phone_number_id}/messages``).

A free-form message (text, buttons) reaches a person only within 24 hours of their last message to the number;
outside that window only an approved template does (``WhatsAppSendError.outside_window``).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.logger import Logger

logger = Logger(__name__)

GRAPH_URL = "https://graph.facebook.com"
TEXT_MAX_LENGTH = 4096
INTERACTIVE_BODY_MAX_LENGTH = 1024
BUTTON_TITLE_MAX_LENGTH = 20
MAX_BUTTONS = 3
# Meta error codes: the recipient has not written in 24 hours (re-engagement) / the window closed.
_OUTSIDE_WINDOW_CODES = frozenset({131047, 470})
_TEMPLATE_WHITESPACE = re.compile(r"[\n\t]+| {4,}")


@dataclass(frozen=True)
class Button:
    """A quick-reply button: ``id`` comes back in the webhook when tapped, ``title`` is what the person sees."""

    id: str
    title: str


class WhatsAppSendError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code

    @property
    def outside_window(self) -> bool:
        """The recipient has not written in 24 hours: only a template message can reach them."""
        return self.code in _OUTSIDE_WINDOW_CODES


class WhatsAppNotConfigured(WhatsAppSendError):
    """No ``WHATSAPP_ACCESS_TOKEN``: nothing can be sent."""


class WhatsAppSender(Protocol):
    """Each method returns the sent message's id (``wamid``) or raises ``WhatsAppSendError``."""

    async def send_text(self, phone_number_id: str, to: str, body: str) -> str: ...

    async def send_buttons(self, phone_number_id: str, to: str, body: str, buttons: Sequence[Button]) -> str: ...

    async def send_template(
        self,
        phone_number_id: str,
        to: str,
        name: str,
        language: str,
        body_params: Sequence[str],
        button_payloads: Sequence[str] = (),
    ) -> str: ...


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _template_param(text: str) -> str:
    """Template parameters may not contain newlines, tabs or four spaces in a row."""
    return _TEMPLATE_WHITESPACE.sub(" ", text).strip()


class WhatsAppCloudClient:
    """``token`` is the Meta system-user token; ``graph_url`` replaces Meta (the local mock, ``app.api.v1.mock``);
    ``http`` replaces the HTTP client (tests)."""

    def __init__(
        self,
        token: str | None,
        graph_version: str,
        http: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
        graph_url: str = GRAPH_URL,
    ) -> None:
        self._token = token
        self._base = f"{graph_url.rstrip('/')}/{graph_version}"
        self._http = http
        self._timeout = timeout

    async def send_text(self, phone_number_id: str, to: str, body: str) -> str:
        return await self._send(phone_number_id, to, "text", {"text": {"body": _clip(body, TEXT_MAX_LENGTH)}})

    async def send_buttons(self, phone_number_id: str, to: str, body: str, buttons: Sequence[Button]) -> str:
        interactive = {
            "type": "button",
            "body": {"text": _clip(body, INTERACTIVE_BODY_MAX_LENGTH)},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b.id, "title": _clip(b.title, BUTTON_TITLE_MAX_LENGTH)}}
                    for b in buttons[:MAX_BUTTONS]
                ]
            },
        }
        return await self._send(phone_number_id, to, "interactive", {"interactive": interactive})

    async def send_template(
        self,
        phone_number_id: str,
        to: str,
        name: str,
        language: str,
        body_params: Sequence[str],
        button_payloads: Sequence[str] = (),
    ) -> str:
        components: list[dict[str, Any]] = [
            {"type": "body", "parameters": [{"type": "text", "text": _template_param(p)} for p in body_params]}
        ]
        components += [
            {"type": "button", "sub_type": "quick_reply", "index": str(index), "parameters": [
                {"type": "payload", "payload": payload}
            ]}
            for index, payload in enumerate(button_payloads)
        ]
        template = {"name": name, "language": {"code": language}, "components": components}
        return await self._send(phone_number_id, to, "template", {"template": template})

    async def _send(self, phone_number_id: str, to: str, kind: str, content: dict[str, Any]) -> str:
        if not self._token:
            raise WhatsAppNotConfigured("WhatsApp is not configured: set WHATSAPP_ACCESS_TOKEN")
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+"), "type": kind}
        url = f"{self._base}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            if self._http is not None:
                response = await self._http.post(url, json=body | content, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    response = await http.post(url, json=body | content, headers=headers)
        except httpx.HTTPError as exc:
            raise WhatsAppSendError(f"WhatsApp request failed: {type(exc).__name__}") from exc
        data = response.json() if response.content else {}
        if response.is_error:
            error = data.get("error") or {}
            code = error.get("code")
            message = error.get("message") or f"HTTP {response.status_code}"
            logger.fire("whatsapp_send_failed", level="warning", kind=kind, status=response.status_code, code=code)
            code = code if isinstance(code, int) else None
            raise WhatsAppSendError(f"WhatsApp rejected the message: {message}", code)
        try:
            message_id: str = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WhatsAppSendError("WhatsApp answered without a message id") from exc
        logger.fire("whatsapp_sent", kind=kind, message_id=message_id)
        return message_id
