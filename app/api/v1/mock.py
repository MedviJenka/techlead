"""A local stand-in for Meta's WhatsApp Cloud API: try the WhatsApp channel end to end without a real number.

It plays both sides of Meta:

- Graph API: the app's sends (``POST /{version}/{phone_number_id}/messages``) are recorded here, never delivered.
- Webhooks: ``POST /mock/inbound`` builds a Meta-shaped delivery, signs it with ``WHATSAPP_APP_SECRET`` and posts it
  to the app's webhook, as if a person had written to the business number. ``POST /mock/tap`` taps a button of a
  recorded send (the owner approving a draft).

Setup, in ``.env`` (both processes read it):

    WHATSAPP_GRAPH_URL=http://localhost:8001
    WHATSAPP_ACCESS_TOKEN=mock          # any value
    WHATSAPP_APP_SECRET=mock-secret     # any value
    WHATSAPP_VERIFY_TOKEN=mock-verify   # any value

Connect a business's WhatsApp number in the app with phone number id ``MOCK_PHONE_NUMBER_ID`` (default
``100000000000001``), then run the API, the worker and this mock:

    uv run python -m app.api.v1.mock

and open http://localhost:8001 for a chat page (JSON routes under ``/mock``, docs at ``/docs``). Optional environment:
``MOCK_PORT`` (8001), ``MOCK_WEBHOOK_URL`` (http://localhost:8000/api/v1/webhooks/whatsapp), ``MOCK_PHONE_NUMBER_ID``.
Everything is kept in memory and lost on restart.

In Docker, ``compose.mock.yml`` runs it as the ``whatsapp-mock`` service and wires the backend and the worker to it:
``docker compose -f compose.yml -f compose.mock.yml up --build``.
"""

import hashlib
import hmac
import json
import os
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.logger import Logger
from settings import get_config

logger = Logger(__name__)

PORT = int(os.environ.get("MOCK_PORT", "8001"))
WEBHOOK_URL = os.environ.get("MOCK_WEBHOOK_URL", "http://localhost:8000/api/v1/webhooks/whatsapp")
PHONE_NUMBER_ID = os.environ.get("MOCK_PHONE_NUMBER_ID", "100000000000001")
WEBHOOK_TIMEOUT = 60.0
WINDOW = timedelta(hours=24)
_PHONE = re.compile(r"^\+?\d{7,15}$")
# Meta error codes the client acts on (app/channels/whatsapp/client.py).
_OUTSIDE_WINDOW_CODE = 131047
_INVALID_PARAMETER_CODE = 100
_AUTH_CODE = 190


class Direction(StrEnum):
    INBOUND = "inbound"  # person -> business number (delivered to the app's webhook)
    OUTBOUND = "outbound"  # business number -> person (sent by the app to this mock)


class MockButton(BaseModel):
    id: str
    title: str


class MockMessage(BaseModel):
    id: str
    direction: Direction
    phone_number_id: str
    contact: str  # the person's number, E.164
    kind: str
    text: str | None
    buttons: list[MockButton] = []
    at: datetime
    status: str  # inbound: the webhook's answer; outbound: "accepted" or the error returned
    raw: dict[str, Any]


class MockSettings(BaseModel):
    enforce_window: bool = Field(
        default=False, description="reject free-form sends to a number that has not written in 24 hours (code 131047)"
    )
    fail_sends: bool = Field(default=False, description="answer every send with a 500, as during a Meta outage")


class InboundRequest(BaseModel):
    sender: str = Field(pattern=_PHONE.pattern, description="the person's number, E.164 (+972501234567)")
    text: str | None = Field(default=None, max_length=4096, description="the message, or a caption for media")
    name: str | None = Field(default="Mock Lead", description="WhatsApp profile name; null sends none")
    kind: Literal["text", "image", "audio", "location", "reaction"] = "text"
    phone_number_id: str = PHONE_NUMBER_ID
    message_id: str | None = Field(default=None, description="reuse an id to replay a delivery (idempotency)")


class TapRequest(BaseModel):
    message_id: str = Field(description="id of a recorded outbound message with buttons")
    button_id: str


class Delivery(BaseModel):
    message: MockMessage
    webhook_status: int | None
    webhook_body: Any


class MockState:
    def __init__(self) -> None:
        self.messages: list[MockMessage] = []
        self.settings = MockSettings()

    def last_inbound(self, contact: str) -> datetime | None:
        return next(
            (m.at for m in reversed(self.messages) if m.direction is Direction.INBOUND and m.contact == contact), None
        )

    def outbound(self, message_id: str) -> MockMessage | None:
        return next((m for m in self.messages if m.direction is Direction.OUTBOUND and m.id == message_id), None)


state = MockState()


def _wamid() -> str:
    return f"wamid.MOCK{uuid.uuid4().hex.upper()}"


def _e164(number: str) -> str:
    return "+" + number.lstrip("+")


def _meta_error(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "OAuthException", "code": code}}, status_code=status)


# --- Graph API: the app's sends ---


def _outbound_content(kind: str, body: dict[str, Any]) -> tuple[str | None, list[MockButton]]:
    """What the person would see: the text, and the buttons they could tap (template buttons answer a payload)."""
    if kind == "text":
        return body.get("text", {}).get("body"), []
    if kind == "interactive":
        interactive = body.get("interactive", {})
        buttons = [
            MockButton(id=b["reply"]["id"], title=b["reply"]["title"])
            for b in interactive.get("action", {}).get("buttons", [])
        ]
        return interactive.get("body", {}).get("text"), buttons
    template = body.get("template", {})
    params, buttons = [], []
    for component in template.get("components", []):
        if component.get("type") == "body":
            params = [p.get("text", "") for p in component.get("parameters", [])]
        elif component.get("type") == "button":
            payload = component["parameters"][0]["payload"]
            buttons.append(MockButton(id=payload, title=payload))
    return f"[template {template.get('name')}] " + " | ".join(params), buttons


async def graph_send(version: str, phone_number_id: str, request: Request) -> JSONResponse:
    """``POST /{version}/{phone_number_id}/messages``, answered the way the Cloud API answers."""
    if not request.headers.get("Authorization", "").startswith("Bearer "):
        return _meta_error(401, _AUTH_CODE, "Missing access token")
    try:
        body: dict[str, Any] = await request.json()
    except ValueError:
        return _meta_error(400, _INVALID_PARAMETER_CODE, "The body is not JSON")
    kind, to = body.get("type"), body.get("to")
    if body.get("messaging_product") != "whatsapp" or not isinstance(to, str) or not _PHONE.match(to):
        return _meta_error(400, _INVALID_PARAMETER_CODE, "Invalid parameter: messaging_product or to")
    if kind not in {"text", "interactive", "template"}:
        return _meta_error(400, _INVALID_PARAMETER_CODE, f"Unsupported message type: {kind}")
    contact, now = _e164(to), datetime.now(UTC)
    text, buttons = _outbound_content(kind, body)
    message = MockMessage(
        id=_wamid(), direction=Direction.OUTBOUND, phone_number_id=phone_number_id, contact=contact, kind=kind,
        text=text, buttons=buttons, at=now, status="accepted", raw=body,
    )
    error: tuple[int, int, str] | None = None
    last = state.last_inbound(contact)
    if state.settings.fail_sends:
        error = 500, 2, "Service temporarily unavailable (mock)"
    elif state.settings.enforce_window and kind != "template" and (last is None or now - last > WINDOW):
        error = 400, _OUTSIDE_WINDOW_CODE, "Re-engagement message: more than 24 hours since the last reply"
    if error is not None:
        message.status = f"rejected: {error[2]}"
    state.messages.append(message)
    logger.fire("mock_whatsapp_send", kind=kind, to=contact, status=message.status, version=version)
    if error is not None:
        return _meta_error(*error)
    return JSONResponse(
        {"messaging_product": "whatsapp", "contacts": [{"input": to, "wa_id": to}], "messages": [{"id": message.id}]}
    )


# --- Webhooks: a person writing to the business number ---


def _inbound_content(request: InboundRequest, wamid: str) -> tuple[dict[str, Any], str | None]:
    if request.kind == "text":
        if not request.text:
            raise HTTPException(422, "A text message needs text")
        return {"text": {"body": request.text}}, request.text
    if request.kind == "image":
        image = {"id": f"mock-media-{wamid[-8:]}", "mime_type": "image/jpeg", "sha256": "mock"}
        return {"image": image | ({"caption": request.text} if request.text else {})}, request.text
    if request.kind == "audio":
        return {"audio": {"id": f"mock-media-{wamid[-8:]}", "mime_type": "audio/ogg; codecs=opus", "voice": True}}, None
    if request.kind == "location":
        return {"location": {"latitude": 32.0853, "longitude": 34.7818, "name": request.text}}, request.text
    last = next((m.id for m in reversed(state.messages) if m.direction is Direction.OUTBOUND), _wamid())
    return {"reaction": {"message_id": last, "emoji": request.text or "\U0001f44d"}}, request.text


async def _deliver(
    phone_number_id: str, sender: str, name: str | None, kind: str, content: dict[str, Any], text: str | None,
    buttons_hint: str | None = None, message_id: str | None = None,
) -> Delivery:
    """Sign a Meta-shaped webhook delivery of one message and post it to the app."""
    secret = get_config().WHATSAPP_APP_SECRET
    if not secret:
        raise HTTPException(503, "Set WHATSAPP_APP_SECRET in .env: the mock signs webhooks with it")
    wa_id, now = sender.lstrip("+"), datetime.now(UTC)
    wamid = message_id or _wamid()
    raw = {"from": wa_id, "id": wamid, "timestamp": str(int(now.timestamp())), "type": kind} | content
    contact: dict[str, Any] = {"wa_id": wa_id} | ({"profile": {"name": name}} if name else {})
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "mock-waba", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "15550000001", "phone_number_id": phone_number_id},
            "contacts": [contact],
            "messages": [raw],
        }}]}],
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    message = MockMessage(
        id=wamid, direction=Direction.INBOUND, phone_number_id=phone_number_id, contact=_e164(sender), kind=kind,
        text=buttons_hint or text, at=now, status="pending", raw=raw,
    )
    state.messages.append(message)
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as http:
            response = await http.post(
                WEBHOOK_URL, content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
            )
    except httpx.HTTPError as exc:
        message.status = f"undelivered: {type(exc).__name__}"
        logger.fire("mock_whatsapp_webhook_failed", level="warning", url=WEBHOOK_URL, error=type(exc).__name__)
        return Delivery(message=message, webhook_status=None, webhook_body=f"Is the API running at {WEBHOOK_URL}?")
    try:
        answer: Any = response.json()
    except ValueError:
        answer = response.text
    message.status = f"webhook {response.status_code}"
    logger.fire("mock_whatsapp_webhook", status=response.status_code, kind=kind, sender=message.contact)
    return Delivery(message=message, webhook_status=response.status_code, webhook_body=answer)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    logger.fire("mock_whatsapp_started", port=PORT, webhook_url=WEBHOOK_URL, phone_number_id=PHONE_NUMBER_ID)
    yield
    logger.fire("mock_whatsapp_stopped")


app = FastAPI(title="Mock WhatsApp Cloud API", lifespan=lifespan)


@app.post("/mock/inbound", tags=["mock"])
async def inbound(request: InboundRequest) -> Delivery:
    """A person writes to the business number: the app receives the webhook Meta would send."""
    wamid = request.message_id or _wamid()
    content, text = _inbound_content(request, wamid)
    return await _deliver(request.phone_number_id, request.sender, request.name, request.kind, content, text,
                          message_id=wamid)


@app.post("/mock/tap", tags=["mock"])
async def tap(request: TapRequest) -> Delivery:
    """The recipient of a recorded send taps one of its buttons (an interactive reply, or a template quick reply)."""
    sent = state.outbound(request.message_id)
    if sent is None:
        raise HTTPException(404, "No such outbound message")
    button = next((b for b in sent.buttons if b.id == request.button_id), None)
    if button is None:
        raise HTTPException(404, "The message has no such button")
    if sent.kind == "interactive":
        kind = "interactive"
        content: dict[str, Any] = {"interactive": {"type": "button_reply", "button_reply": button.model_dump()}}
    else:
        kind = "button"
        content = {"button": {"text": button.title, "payload": button.id}}
    content["context"] = {"from": "15550000001", "id": sent.id}
    return await _deliver(sent.phone_number_id, sent.contact, None, kind, content, button.title,
                          buttons_hint=f"[tapped] {button.title}")


@app.get("/mock/messages", tags=["mock"])
async def messages(contact: str | None = None) -> list[MockMessage]:
    """Every recorded message, oldest first; ``contact`` (E.164) keeps one conversation."""
    return [m for m in state.messages if contact is None or m.contact == _e164(contact)]


@app.delete("/mock/messages", tags=["mock"], status_code=204)
async def clear_messages() -> None:
    state.messages.clear()


@app.get("/mock/settings", tags=["mock"])
async def get_settings() -> MockSettings:
    return state.settings


@app.put("/mock/settings", tags=["mock"])
async def put_settings(settings: MockSettings) -> MockSettings:
    state.settings = settings
    return settings


@app.post("/mock/verify", tags=["mock"])
async def verify() -> dict[str, Any]:
    """Run Meta's subscription handshake against the app's webhook (``WHATSAPP_VERIFY_TOKEN``)."""
    challenge = uuid.uuid4().hex
    params = {"hub.mode": "subscribe", "hub.verify_token": get_config().WHATSAPP_VERIFY_TOKEN or "",
              "hub.challenge": challenge}
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.get(WEBHOOK_URL, params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Is the API running at {WEBHOOK_URL}? ({type(exc).__name__})") from exc
    return {"verified": response.status_code == 200 and response.text == challenge, "status": response.status_code}


app.add_api_route("/{version}/{phone_number_id}/messages", graph_send, methods=["POST"], tags=["graph"])


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def page() -> str:
    return _PAGE.replace("__PHONE_NUMBER_ID__", PHONE_NUMBER_ID).replace("__WEBHOOK_URL__", WEBHOOK_URL)


_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mock WhatsApp</title>
<style>
  :root { --bg:#efeae2; --panel:#fff; --in:#fff; --out:#d9fdd3; --text:#111b21; --muted:#667781; --accent:#008069; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0b141a; --panel:#202c33; --in:#202c33; --out:#005c4b; --text:#e9edef; --muted:#8696a0; }
  }
  * { box-sizing:border-box } body { margin:0; font:14px system-ui,sans-serif; background:var(--bg); color:var(--text) }
  header { background:var(--accent); color:#fff; padding:10px 16px }
  header small { opacity:.8 } main { max-width:820px; margin:0 auto; padding:12px 16px 140px }
  .msg { max-width:75%; margin:6px 0; padding:8px 10px; border-radius:8px; background:var(--in); white-space:pre-wrap;
         word-wrap:break-word; box-shadow:0 1px 1px #0002 }
  .outbound { background:var(--out); margin-left:auto }
  .meta { color:var(--muted); font-size:11px; margin-bottom:4px; cursor:pointer }
  .buttons button { margin:6px 6px 0 0; padding:5px 10px; border:1px solid var(--accent); background:transparent;
                    color:var(--text); border-radius:14px; cursor:pointer }
  form { position:fixed; bottom:0; left:0; right:0; background:var(--panel); padding:10px 16px; display:flex;
         flex-wrap:wrap; gap:8px; justify-content:center; box-shadow:0 -1px 3px #0003 }
  input, select, form button { padding:8px; border-radius:6px; border:1px solid #8886; background:var(--bg);
                               color:var(--text) }
  #text { flex:1 1 260px } form button { background:var(--accent); color:#fff; border:none; cursor:pointer }
  label { display:flex; align-items:center; gap:4px; color:var(--muted); font-size:12px }
</style></head>
<body>
<header><b>Mock WhatsApp</b> <small>number id __PHONE_NUMBER_ID__ &rarr; __WEBHOOK_URL__</small></header>
<main id="log"></main>
<form id="send">
  <input id="sender" placeholder="from +972501234567" required size="16">
  <input id="name" placeholder="profile name" value="Mock Lead" size="12">
  <select id="kind"><option>text</option><option>image</option><option>audio</option><option>location</option>
    <option>reaction</option></select>
  <input id="text" placeholder="message">
  <button>Send</button>
  <label><input type="checkbox" id="window"> enforce 24h window</label>
  <label><input type="checkbox" id="fail"> fail sends</label>
  <label><input type="checkbox" id="only"> only this number</label>
  <button type="button" id="clear">Clear</button>
</form>
<script>
const $ = id => document.getElementById(id);
async function api(path, method = "GET", body) {
  const r = await fetch(path, {method, headers: {"Content-Type": "application/json"},
                               body: body && JSON.stringify(body)});
  const data = r.status === 204 ? null : await r.json();
  if (!r.ok) alert(JSON.stringify(data.detail || data));
  return data;
}
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls;
  if (text != null) e.textContent = text; return e; }
let last = "";
async function refresh() {
  const only = $("only").checked && $("sender").value;
  const messages = await api("/mock/messages" + (only ? "?contact=" + encodeURIComponent(only) : ""));
  const key = JSON.stringify(messages); if (key === last) return; last = key;
  const log = $("log"); log.replaceChildren();
  for (const m of messages) {
    const box = el("div", "msg " + m.direction);
    const meta = el("div", "meta", (m.direction === "inbound" ? m.contact + " \\u2192 business" : "business \\u2192 "
      + m.contact) + " \\u00b7 " + m.kind + " \\u00b7 " + new Date(m.at).toLocaleTimeString() + " \\u00b7 " + m.status);
    meta.title = "use this number"; meta.onclick = () => { $("sender").value = m.contact; };
    box.append(meta, el("div", "", m.text ?? "(" + m.kind + ")"));
    if (m.buttons.length) {
      const row = el("div", "buttons");
      for (const b of m.buttons) { const btn = el("button", "", b.title); btn.type = "button";
        btn.onclick = () => api("/mock/tap", "POST", {message_id: m.id, button_id: b.id}).then(refresh);
        row.append(btn); }
      box.append(row);
    }
    log.append(box);
  }
  window.scrollTo(0, document.body.scrollHeight);
}
$("send").onsubmit = async e => {
  e.preventDefault();
  await api("/mock/inbound", "POST", {sender: $("sender").value, name: $("name").value || null,
    kind: $("kind").value, text: $("text").value || null});
  $("text").value = ""; refresh();
};
async function saveSettings() { await api("/mock/settings", "PUT",
  {enforce_window: $("window").checked, fail_sends: $("fail").checked}); }
$("window").onchange = saveSettings; $("fail").onchange = saveSettings;
$("only").onchange = () => { last = ""; refresh(); };
$("clear").onclick = async () => { await api("/mock/messages", "DELETE"); refresh(); };
api("/mock/settings").then(s => { $("window").checked = s.enforce_window; $("fail").checked = s.fail_sends; });
refresh(); setInterval(refresh, 2000);
</script>
</body></html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
