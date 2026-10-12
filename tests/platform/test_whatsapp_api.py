"""The WhatsApp HTTP surface: Meta's webhook (handshake, signature, redelivery on failure) and the dashboard's
WhatsApp settings and approval queue. No database: services run on the in-memory repositories.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai.schemas import Channel
from app.api.deps import get_reply_service, get_whatsapp_inbox, require_business_access
from app.core.auth import AuthUser, current_user
from app.main import create_app
from app.models import Business
from app.services.inbox import InboxError
from app.services.lead import LeadService
from app.services.replies import ReplyService
from settings import get_config
from tests.platform.memory import (
    OWNER_PHONE,
    FakeAccounts,
    FakeSender,
    FakeStore,
    make_account,
    make_business,
    make_replies,
    make_service,
)
from tests.platform.test_whatsapp_channel import SECRET, delivery, sign, text
from tests.platform.test_whatsapp_flow import inbound

LEAD_PHONE = "+972521234567"


class RecordingInbox:
    def __init__(self, error: Exception | None = None) -> None:
        self.payloads: list[Any] = []
        self.error = error

    async def handle(self, payload: Any) -> None:
        self.payloads.append(payload)
        if self.error:
            raise self.error


@pytest.fixture(autouse=True)
def whatsapp_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    config = get_config()
    monkeypatch.setattr(config, "WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setattr(config, "WHATSAPP_VERIFY_TOKEN", "verify-me")
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "token")


async def _client(overrides: dict[Any, Any]) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides.update(overrides)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def inbox() -> RecordingInbox:
    return RecordingInbox()


@pytest.fixture
async def webhook(inbox: RecordingInbox) -> AsyncIterator[AsyncClient]:
    async for client in _client({get_whatsapp_inbox: lambda: inbox}):
        yield client


@pytest.fixture
def path(api_prefix: str) -> str:
    return f"{api_prefix}/webhooks/whatsapp"


# --- webhook ---


async def test_subscription_handshake_echoes_the_challenge(webhook: AsyncClient, path: str) -> None:
    params = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "1158201444"}
    response = await webhook.get(path, params=params)
    assert (response.status_code, response.text) == (200, "1158201444")


async def test_handshake_with_a_wrong_token_is_refused(webhook: AsyncClient, path: str) -> None:
    params = {"hub.mode": "subscribe", "hub.verify_token": "guess", "hub.challenge": "1"}
    assert (await webhook.get(path, params=params)).status_code == 403


async def test_signed_delivery_reaches_the_inbox(webhook: AsyncClient, path: str, inbox: RecordingInbox) -> None:
    body = json.dumps(delivery(text("Hi"))).encode()
    response = await webhook.post(path, content=body, headers={"X-Hub-Signature-256": sign(body)})
    assert response.status_code == 200
    assert inbox.payloads == [json.loads(body)]


async def test_unsigned_or_forged_deliveries_are_rejected(
    webhook: AsyncClient, path: str, inbox: RecordingInbox
) -> None:
    body = json.dumps(delivery(text("Hi"))).encode()
    assert (await webhook.post(path, content=body)).status_code == 401
    forged = {"X-Hub-Signature-256": sign(body, "someone-else")}
    assert (await webhook.post(path, content=body, headers=forged)).status_code == 401
    assert inbox.payloads == []


async def test_without_an_app_secret_the_webhook_is_closed(
    webhook: AsyncClient, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_config(), "WHATSAPP_APP_SECRET", None)
    body = b"{}"
    assert (await webhook.post(path, content=body, headers={"X-Hub-Signature-256": sign(body)})).status_code == 503


async def test_a_failed_message_answers_an_error_so_meta_redelivers(path: str) -> None:
    inbox = RecordingInbox(InboxError("1 WhatsApp message(s) failed"))
    async for client in _client({get_whatsapp_inbox: lambda: inbox}):
        body = json.dumps(delivery(text("Hi"))).encode()
        response = await client.post(path, content=body, headers={"X-Hub-Signature-256": sign(body)})
        assert response.status_code == 500


# --- dashboard: WhatsApp settings and approvals ---


@pytest.fixture
def business() -> Business:
    return make_business({"phone_region": "IL"})


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def service(business: Business, store: FakeStore) -> LeadService:
    return make_service(business, store)


@pytest.fixture
def replies(service: LeadService, sender: FakeSender) -> ReplyService:
    return make_replies(service, FakeAccounts(), sender)


@pytest.fixture
async def dashboard(replies: ReplyService) -> AsyncIterator[AsyncClient]:
    async def no_check() -> None:
        return None

    overrides = {
        current_user: lambda: AuthUser(id="00000000-0000-0000-0000-000000000001", email="owner@example.com"),
        require_business_access: no_check,
        get_reply_service: lambda: replies,
    }
    async for client in _client(overrides):
        yield client


async def test_connect_whatsapp_then_read_the_status(
    dashboard: AsyncClient, api_prefix: str, business: Business
) -> None:
    url = f"{api_prefix}/businesses/{business.id}/whatsapp"
    before = (await dashboard.get(url)).json()
    assert (before["connection"], before["configured"]) == (None, True)
    assert before["webhook_path"] == f"{api_prefix}/webhooks/whatsapp"

    saved = await dashboard.put(url, json={"phone_number_id": "1098765432", "owner_phone": "+972 50-111-1111"})
    assert saved.status_code == 200
    assert saved.json()["owner_phone"] == OWNER_PHONE
    assert (await dashboard.get(url)).json()["connection"]["phone_number_id"] == "1098765432"

    assert (await dashboard.delete(url)).status_code == 204
    assert (await dashboard.get(url)).json()["connection"] is None


async def test_auto_send_is_off_until_a_timeout_is_set(
    dashboard: AsyncClient, api_prefix: str, business: Business
) -> None:
    url = f"{api_prefix}/businesses/{business.id}/whatsapp"
    connection = {"phone_number_id": "1098765432", "owner_phone": "+972501111111"}
    assert (await dashboard.put(url, json=connection)).json()["auto_send_after_minutes"] is None

    saved = await dashboard.put(url, json=connection | {"auto_send_after_minutes": 10})
    assert saved.json()["auto_send_after_minutes"] == 10
    for minutes in (0, 24 * 60 + 1):
        assert (await dashboard.put(url, json=connection | {"auto_send_after_minutes": minutes})).status_code == 422


async def test_owner_phone_must_be_international(dashboard: AsyncClient, api_prefix: str, business: Business) -> None:
    url = f"{api_prefix}/businesses/{business.id}/whatsapp"
    response = await dashboard.put(url, json={"phone_number_id": "1098765432", "owner_phone": "0501111111"})
    assert response.status_code == 422
    assert "international" in response.json()["error"]["message"]


async def test_dashboard_approves_and_rejects_from_the_queue(
    dashboard: AsyncClient,
    api_prefix: str,
    business: Business,
    service: LeadService,
    replies: ReplyService,
    sender: FakeSender,
) -> None:
    await replies.accounts.save(business.id, make_account(business).model_dump())
    received = await service.receive_message(business.id, inbound())
    assert received is not None
    lead = received[0]
    first = await replies.create_draft(business.id, lead.id, Channel.WHATSAPP, "Hi Dana!", None)
    assert first is not None
    base = f"{api_prefix}/businesses/{business.id}"

    queue = (await dashboard.get(f"{base}/replies")).json()
    assert [(d["id"], d["lead_name"]) for d in queue] == [(str(first.id), "Dana Levi")]

    approved = await dashboard.post(f"{base}/replies/{first.id}/approve", json={"message": " Hi Dana, which area? "})
    assert approved.status_code == 200
    assert (approved.json()["status"], approved.json()["edited"]) == ("sent", True)
    assert sender.to(LEAD_PHONE) == ["Hi Dana, which area?"]
    assert (await dashboard.get(f"{base}/replies")).json() == []

    again = await dashboard.post(f"{base}/replies/{first.id}/reject")
    assert again.status_code == 409

    second = await replies.create_draft(business.id, lead.id, Channel.WHATSAPP, "Following up", None)
    assert second is not None
    rejected = await dashboard.post(f"{base}/replies/{second.id}/reject")
    assert rejected.json()["status"] == "rejected"
    history = (await dashboard.get(f"{base}/leads/{lead.id}/replies")).json()
    assert [d["status"] for d in history] == ["rejected", "sent"]
