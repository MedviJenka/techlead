"""The WhatsApp transport (app/channels/whatsapp): webhook signature and parsing, and the Cloud API client."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.channels.whatsapp import (
    Button,
    WhatsAppCloudClient,
    WhatsAppNotConfigured,
    WhatsAppSendError,
    parse_messages,
    verify_signature,
)

SECRET = "app-secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def delivery(*messages: dict[str, Any], phone_number_id: str = "1098765432", **value: Any) -> dict[str, Any]:
    """A webhook body as Meta sends it."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "972500000000", "phone_number_id": phone_number_id},
                    "contacts": [{"profile": {"name": "Dana Levi"}, "wa_id": "972521234567"}],
                    "messages": list(messages),
                } | value,
            }],
        }],
    }


def text(body: str, message_id: str = "wamid.A", sender: str = "972521234567") -> dict[str, Any]:
    return {"from": sender, "id": message_id, "timestamp": "1791547200", "type": "text", "text": {"body": body}}


def button_reply(reply_id: str, message_id: str = "wamid.B", sender: str = "972501111111") -> dict[str, Any]:
    return {
        "from": sender, "id": message_id, "timestamp": "1791547200", "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": reply_id, "title": "Approve"}},
    }


# --- signature ---


def test_signature_of_the_raw_body_is_accepted() -> None:
    body = json.dumps(delivery(text("hi"))).encode()
    assert verify_signature(SECRET, body, sign(body))


@pytest.mark.parametrize("header", [None, "", "sha1=abc", "sha256=" + "0" * 64])
def test_missing_or_wrong_signatures_are_refused(header: str | None) -> None:
    assert not verify_signature(SECRET, b"{}", header)


def test_a_body_changed_after_signing_is_refused() -> None:
    assert not verify_signature(SECRET, b'{"a": 2}', sign(b'{"a": 1}'))


# --- parsing ---


def test_text_message_is_parsed_with_e164_sender_and_profile_name() -> None:
    [message] = parse_messages(delivery(text("  Looking for a 4-room flat  ")))
    assert message.phone_number_id == "1098765432"
    assert (message.message_id, message.sender, message.profile_name) == ("wamid.A", "+972521234567", "Dana Levi")
    assert (message.kind, message.text, message.reply_id) == ("text", "Looking for a 4-room flat", None)
    assert message.sent_at == datetime.fromtimestamp(1791547200, UTC)


def test_tapped_buttons_carry_their_id() -> None:
    template_button = {
        "from": "972501111111", "id": "wamid.C", "timestamp": "1791547200", "type": "button",
        "button": {"payload": "reject:abc", "text": "Reject"},
    }
    interactive, template = parse_messages(delivery(button_reply("approve:abc"), template_button))
    assert (interactive.kind, interactive.reply_id, interactive.text) == ("interactive", "approve:abc", "Approve")
    assert (template.kind, template.reply_id, template.text) == ("button", "reject:abc", "Reject")


def test_media_messages_have_no_text() -> None:
    image = {"from": "972521234567", "id": "wamid.D", "timestamp": "1", "type": "image", "image": {"id": "m"}}
    [message] = parse_messages(delivery(image))
    assert (message.kind, message.text) == ("image", None)


def test_status_updates_and_other_fields_carry_no_messages() -> None:
    statuses = delivery(statuses=[{"id": "wamid.X", "status": "delivered"}])
    statuses["entry"][0]["changes"][0]["value"].pop("messages")
    other = {"entry": [{"changes": [{"field": "account_update", "value": {}}]}]}
    assert parse_messages(statuses) == []
    assert parse_messages(other) == []


@pytest.mark.parametrize("payload", [None, [], "x", {"entry": "x"}, {"entry": [{"changes": [None]}]}])
def test_malformed_deliveries_parse_to_nothing(payload: Any) -> None:
    assert parse_messages(payload) == []


def test_a_malformed_message_is_skipped_and_the_rest_kept() -> None:
    no_id = {"from": "972521234567", "type": "text", "text": {"body": "x"}}
    bad_sender = text("x", "wamid.E", sender="not-a-number")
    messages = parse_messages(delivery(no_id, bad_sender, text("ok", "wamid.F")))
    assert [m.message_id for m in messages] == ["wamid.F"]


# --- client ---


class Graph:
    """A fake Graph API: records requests and answers with ``response``."""

    def __init__(self, status: int = 200, body: dict[str, Any] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status
        self.body = body if body is not None else {"messages": [{"id": "wamid.SENT"}]}

    def client(self, token: str | None = "token") -> WhatsAppCloudClient:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status, json=self.body)

        return WhatsAppCloudClient(token, "v23.0", http=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    def sent(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)


async def test_text_is_posted_to_the_number_with_the_token() -> None:
    graph = Graph()
    assert await graph.client().send_text("1098765432", "+972521234567", "Hello Dana") == "wamid.SENT"
    request = graph.requests[-1]
    assert str(request.url) == "https://graph.facebook.com/v23.0/1098765432/messages"
    assert request.headers["Authorization"] == "Bearer token"
    assert graph.sent() == {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": "972521234567", "type": "text",
        "text": {"body": "Hello Dana"},
    }


async def test_buttons_are_capped_at_three_with_short_titles() -> None:
    graph = Graph()
    buttons = [Button(f"b{i}", "A very long button title") for i in range(4)]
    await graph.client().send_buttons("1", "+972521234567", "Approve?", buttons)
    action = graph.sent()["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in action] == ["b0", "b1", "b2"]
    assert all(len(b["reply"]["title"]) <= 20 for b in action)


async def test_template_parameters_lose_newlines_and_buttons_get_payloads() -> None:
    graph = Graph()
    await graph.client().send_template("1", "+1", "lead_reply_approval", "en", ["Dana", "Hi!\n\nWhen?"], ["a", "b"])
    components = graph.sent()["template"]["components"]
    assert components[0]["parameters"] == [{"type": "text", "text": "Dana"}, {"type": "text", "text": "Hi! When?"}]
    assert [(c["index"], c["parameters"][0]["payload"]) for c in components[1:]] == [("0", "a"), ("1", "b")]


async def test_outside_the_24_hour_window_is_recognised() -> None:
    graph = Graph(400, {"error": {"code": 131047, "message": "Re-engagement message"}})
    with pytest.raises(WhatsAppSendError) as raised:
        await graph.client().send_text("1", "+1", "hi")
    assert raised.value.outside_window
    assert "Re-engagement message" in str(raised.value)


async def test_other_errors_and_answers_without_an_id_fail() -> None:
    with pytest.raises(WhatsAppSendError) as raised:
        await Graph(500, {}).client().send_text("1", "+1", "hi")
    assert not raised.value.outside_window
    with pytest.raises(WhatsAppSendError):
        await Graph(200, {"messages": []}).client().send_text("1", "+1", "hi")


async def test_nothing_is_sent_without_a_token() -> None:
    graph = Graph()
    with pytest.raises(WhatsAppNotConfigured):
        await graph.client(token=None).send_text("1", "+1", "hi")
    assert graph.requests == []
