"""
The local WhatsApp mock (app/api/v1/mock.py): a person's message goes through the app's real webhook (signature
check included), the app's sends are recorded, and tapping a recorded button answers the app. No database, no AI:
the webhook's inbox only records what it receives.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_whatsapp_inbox
from app.api.v1 import mock
from app.main import create_app
from settings import get_config
from tests.platform.test_whatsapp_api import RecordingInbox
from tests.platform.test_whatsapp_channel import SECRET

LEAD_PHONE = "+972521234567"


@pytest.fixture(autouse=True)
def fresh_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_config(), "WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setattr(mock, "state", mock.MockState())


@pytest.fixture
def inbox() -> RecordingInbox:
    return RecordingInbox()


@pytest.fixture
async def whatsapp(
    monkeypatch: pytest.MonkeyPatch, inbox: RecordingInbox, api_prefix: str
) -> AsyncIterator[AsyncClient]:
    """A client of the mock, whose webhook deliveries reach the app in-process instead of over the network."""
    app = create_app()
    app.dependency_overrides[get_whatsapp_inbox] = lambda: inbox
    monkeypatch.setattr(mock, "WEBHOOK_URL", f"http://app{api_prefix}/webhooks/whatsapp")
    monkeypatch.setattr(
        mock.httpx, "AsyncClient", lambda **_: AsyncClient(transport=ASGITransport(app=app), base_url="http://app")
    )
    async with AsyncClient(transport=ASGITransport(app=mock.app), base_url="http://mock") as client:
        yield client


async def send_message(client: AsyncClient, text: str, sender: str = LEAD_PHONE, **fields: Any) -> dict[str, Any]:
    """A person writes to the business number through the mock; returns the mock's delivery report."""
    response = await client.post("/mock/inbound", json={"sender": sender, "text": text, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def delivered_message(payload: Any) -> dict[str, Any]:
    value = payload["entry"][0]["changes"][0]["value"]
    return {"contact": value["contacts"][0], "message": value["messages"][0]}


@pytest.mark.parametrize("text", ["Hi, can we talk this week?", "שלום, כמה זה עולה?"])
async def test_a_sent_message_reaches_the_app_signed_and_intact(
    whatsapp: AsyncClient, inbox: RecordingInbox, text: str
) -> None:
    report = await send_message(whatsapp, text, name="Dana Levi")

    assert report["webhook_status"] == 200
    assert report["message"]["status"] == "webhook 200"
    [payload] = inbox.payloads
    delivered = delivered_message(payload)
    assert delivered["message"]["text"] == {"body": text}
    assert delivered["message"]["from"] == LEAD_PHONE.lstrip("+")
    assert delivered["contact"]["profile"] == {"name": "Dana Levi"}


async def test_messages_are_recorded_per_conversation(whatsapp: AsyncClient) -> None:
    await send_message(whatsapp, "First")
    await send_message(whatsapp, "Second")
    await send_message(whatsapp, "Someone else", sender="+972537778899")

    response = await whatsapp.get("/mock/messages", params={"contact": LEAD_PHONE})

    assert [m["text"] for m in response.json()] == ["First", "Second"]


async def test_a_replayed_message_keeps_its_id(whatsapp: AsyncClient, inbox: RecordingInbox) -> None:
    first = await send_message(whatsapp, "Hello")
    await send_message(whatsapp, "Hello", message_id=first["message"]["id"])

    ids = [delivered_message(payload)["message"]["id"] for payload in inbox.payloads]
    assert ids == [first["message"]["id"]] * 2


async def test_a_text_message_needs_text(whatsapp: AsyncClient, inbox: RecordingInbox) -> None:
    response = await whatsapp.post("/mock/inbound", json={"sender": LEAD_PHONE, "text": ""})

    assert response.status_code == 422
    assert inbox.payloads == []


async def test_tapping_a_sent_button_answers_the_app(whatsapp: AsyncClient, inbox: RecordingInbox) -> None:
    sent = await whatsapp.post(
        "/v21.0/100000000000001/messages",
        headers={"Authorization": "Bearer token"},
        json={
            "messaging_product": "whatsapp",
            "to": LEAD_PHONE.lstrip("+"),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Send this reply?"},
                "action": {"buttons": [{"type": "reply", "reply": {"id": "approve:1", "title": "Approve"}}]},
            },
        },
    )
    assert sent.status_code == 200
    message_id = sent.json()["messages"][0]["id"]

    tapped = await whatsapp.post("/mock/tap", json={"message_id": message_id, "button_id": "approve:1"})

    assert tapped.json()["webhook_status"] == 200
    reply = delivered_message(inbox.payloads[-1])["message"]
    assert reply["interactive"]["button_reply"] == {"id": "approve:1", "title": "Approve"}
    assert reply["context"]["id"] == message_id


async def test_a_send_without_a_token_is_refused_like_meta(whatsapp: AsyncClient) -> None:
    response = await whatsapp.post("/v21.0/100000000000001/messages", json={"messaging_product": "whatsapp"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == 190


async def test_when_the_app_is_down_the_message_is_kept_as_undelivered(
    whatsapp: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(mock.httpx, "AsyncClient", lambda **_: AsyncClient(transport=httpx.MockTransport(refuse)))

    report = await send_message(whatsapp, "Anyone there?")

    assert report["webhook_status"] is None
    assert report["message"]["status"] == "undelivered: ConnectError"
