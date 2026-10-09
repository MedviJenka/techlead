"""Run LeadIntelligenceCrew on a sample lead with the configured LLM. Makes real, billed LLM calls.

    python -m ai.crews.lead_intelligence lead_008
"""

import sys

from ai.crews.base import AIRuntime
from ai.crews.lead_intelligence.crew import LeadIntelligenceCrew
from ai.data.sample_store import SAMPLE_BUSINESS, load_sample_store


def main(lead_id: str = "lead_008") -> None:
    store = load_sample_store()
    crew = LeadIntelligenceCrew.for_business(AIRuntime.from_env(store), SAMPLE_BUSINESS.id)
    lead = store.get_lead(SAMPLE_BUSINESS.id, lead_id)
    result = crew.analyze(lead, store.list_activities(SAMPLE_BUSINESS.id, lead_id))
    print(f"\nLead: {lead.full_name}")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:2])
