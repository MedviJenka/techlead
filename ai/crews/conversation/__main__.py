"""Analyze an inbound message from a sample lead, then draft a reply. Makes real, billed LLM calls.

    python -m ai.crews.conversation lead_008 "Looks good, call me on Sunday."
"""

import sys
from datetime import UTC, datetime

from ai.crews.base import AIRuntime
from ai.crews.conversation.crew import ConversationCrew
from ai.data.sample_store import SAMPLE_BUSINESS, load_sample_store
from ai.schemas import Channel, InboundMessage


def main(lead_id: str = "lead_008", body: str = "Looks good. I need to check with my partner. Call me Sunday.") -> None:
    store = load_sample_store()
    crew = ConversationCrew.for_business(AIRuntime.from_env(store), SAMPLE_BUSINESS.id)
    lead = store.get_lead(SAMPLE_BUSINESS.id, lead_id)
    activities = store.list_activities(SAMPLE_BUSINESS.id, lead_id)
    message = InboundMessage(channel=Channel.WHATSAPP, received_at=datetime.now(UTC), body=body)
    insights = crew.analyze_message(lead, message, activities)
    print(insights.model_dump_json(indent=2))
    draft = crew.draft_followup(lead, Channel.WHATSAPP, insights=insights, activities=activities)
    print(draft.model_dump_json(indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:3])
