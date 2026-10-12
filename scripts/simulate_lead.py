"""Play a customer: send a WhatsApp message to the platform through the local mock and watch what comes back.

Needs the stack running with the mock (``docker compose -f compose.yaml -f compose.mock.yaml up``) and a business
connected to the mock's number id. Then:

    uv run python scripts/simulate_lead.py                                   # a new lead, Hebrew sample message
    uv run python scripts/simulate_lead.py "Hi, is the flat still available?" --name "Dana Levi"
    uv run python scripts/simulate_lead.py "ועוד שאלה" --from +972583200999   # the same customer again

Each run without ``--from`` is a new phone number, so a new lead: the worker analyses it and drafts a first reply.
A number that already has a lead only adds the message to its history (no new draft).

The script prints every message the platform sends while it waits: the approval request to the owner, the reply to
the lead (once approved, or sent automatically when auto-send is on in Settings → WhatsApp), and notices to the
owner. It stops when the lead gets a reply, or after ``--wait`` minutes.
"""

import argparse
import random
import sys
import time
import httpx

DEFAULT_TEXT = "שלום, ראיתי את המודעה שלכם. אני מחפשת דירת 4 חדרים בתל אביב, אפשר לתאם צפייה השבוע?"

POLL_SECONDS = 3


def _new_number() -> str:
    return f"+97258{random.randint(1_000_000, 9_999_999)}"


def _show(message: dict, lead: str) -> None:
    at = message["at"][11:19]
    to = "LEAD" if message["contact"] == lead else f"OWNER {message['contact']}"
    print(f"\n[{at}] platform → {to} ({message['kind']}, {message['status']})")
    print(f"  {(message['text'] or '').replace(chr(10), chr(10) + '  ')}")
    if message["buttons"]:
        print(f"  buttons: {' | '.join(b['title'] for b in message['buttons'])}  (tap them on the mock's chat page)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT, help="what the customer writes")
    parser.add_argument("--from", dest="sender", default=None, help="the customer's number, E.164 (default: a new one)")
    parser.add_argument("--name", default="דנה כהן", help="the customer's WhatsApp profile name")
    parser.add_argument("--mock", default="http://localhost:8001", help="the WhatsApp mock's URL")
    parser.add_argument("--wait", type=float, default=15, help="minutes to watch for replies (0: send and exit)")
    args = parser.parse_args()
    sender = args.sender or _new_number()

    with httpx.Client(base_url=args.mock, timeout=70) as mock:
        seen = {m["id"] for m in mock.get("/mock/messages").json()}
        try:
            report = mock.post("/mock/inbound", json={"sender": sender, "name": args.name, "text": args.text}).json()
        except httpx.ConnectError:
            print(f"The mock is not running at {args.mock}.", file=sys.stderr)
            return 1
        if "message" not in report:
            print(f"The mock refused the message: {report}", file=sys.stderr)
            return 1
        print(f"customer {sender} ({args.name}) → platform:\n  {args.text}")
        print(f"platform answered the webhook: {report['webhook_status']} {report['webhook_body']}")
        if report["webhook_status"] != 200:
            return 1
        seen.add(report["message"]["id"])

        deadline = time.monotonic() + args.wait * 60
        if args.wait:
            print(f"\nwatching for up to {args.wait:g} min (Ctrl+C to stop)...")
        while time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            new = [m for m in mock.get("/mock/messages").json() if m["id"] not in seen and m["direction"] == "outbound"]
            for message in new:
                seen.add(message["id"])
                _show(message, sender)
            if any(m["contact"] == sender for m in new):
                print("\nthe lead got a reply.")
                return 0
        if args.wait:
            print("\nno reply to the lead yet. Is the worker running, and is this a new number?")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # Hebrew on the Windows console
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
