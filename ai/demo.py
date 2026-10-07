"""Run LeadIntelligenceCrew on a sample lead with the configured LLM.

    python -m ai.demo lead_008

Requires OPENAI_MODEL (and the provider's API key) in .env. Makes real LLM calls.
"""

import sys

from ai.config import LLMSettings
from ai.data.sample_store import SAMPLE_BUSINESS, load_sample_store
from ai.factory import BusinessCrewFactory


def main(lead_id: str = "lead_008") -> None:
    store = load_sample_store()
    factory = BusinessCrewFactory(store, LLMSettings.from_env().resolver(), verbose=True)
    lead = store.get_lead(SAMPLE_BUSINESS.id, lead_id)
    result = factory.lead_intelligence_crew(SAMPLE_BUSINESS.id).analyze(
        lead, store.list_activities(SAMPLE_BUSINESS.id, lead_id)
    )
    print(f"\nLead: {lead.full_name}")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:2])
