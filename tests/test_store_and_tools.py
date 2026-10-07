import json

import pytest

from ai.data.sample_store import InMemoryLeadStore
from ai.ports import NotFoundError
from ai.schemas import BusinessProfile, LeadSearchFilter, LeadSnapshot, LeadSortField
from ai.tools import GetBusinessMetricsTool, GetLeadActivitiesTool, GetLeadTool, SearchBusinessLeadsTool
from tests.conftest import BUSINESS_ID


def test_sample_leads_are_normalized(store: InMemoryLeadStore, tomer: LeadSnapshot) -> None:
    assert tomer.full_name == "Tomer Katz"
    assert tomer.company_name == "Katz Insurance"
    assert tomer.budget == 90000
    assert tomer.custom_fields["number_of_agents"] == 18


def test_prompt_json_hides_previous_ai_opinions(tomer: LeadSnapshot) -> None:
    data = json.loads(tomer.to_prompt_json())
    assert "lead_score" not in data and "ai_summary" not in data
    assert data["timeframe"] == "immediate"


def test_search_filters_and_sorts(store: InMemoryLeadStore) -> None:
    leads = store.search_leads(BUSINESS_ID, LeadSearchFilter(min_score=80, budget_known=True, sort_by=LeadSortField.SCORE))
    assert [lead.id for lead in leads] == ["lead_008", "lead_003", "lead_001", "lead_005", "lead_009"]


def test_search_not_contacted(store: InMemoryLeadStore) -> None:
    leads = store.search_leads(BUSINESS_ID, LeadSearchFilter(not_contacted_for_days=1))
    assert {lead.id for lead in leads} == {"lead_001", "lead_006", "lead_010"}


def test_pipeline_metrics(store: InMemoryLeadStore) -> None:
    metrics = store.get_pipeline_metrics(BUSINESS_ID)
    assert metrics.total_leads == 10
    assert metrics.hot_leads_not_contacted == 1  # lead_001
    assert metrics.by_status["qualified"] == 2


class TestTenantIsolation:
    @pytest.fixture
    def two_tenant_store(self, store: InMemoryLeadStore, tomer: LeadSnapshot) -> InMemoryLeadStore:
        other = BusinessProfile(id="biz_other", slug="other", name="Other")
        secret = tomer.model_copy(update={"id": "lead_secret", "business_id": "biz_other", "notes": "secret"})
        return InMemoryLeadStore([store.get_business(BUSINESS_ID), other], [tomer, secret])

    def test_tool_cannot_read_other_business_lead(self, two_tenant_store: InMemoryLeadStore) -> None:
        tool = GetLeadTool.bind(two_tenant_store, BUSINESS_ID)
        assert tool.run(lead_id="lead_secret").startswith("ERROR")
        assert "Tomer" in tool.run(lead_id="lead_008")

    def test_search_is_business_scoped(self, two_tenant_store: InMemoryLeadStore) -> None:
        result = SearchBusinessLeadsTool.bind(two_tenant_store, BUSINESS_ID).run(text="")
        assert "lead_secret" not in result and "lead_008" in result

    def test_business_id_is_not_a_tool_argument(self) -> None:
        for tool in (GetLeadTool, GetLeadActivitiesTool, SearchBusinessLeadsTool, GetBusinessMetricsTool):
            fields = tool.model_fields["args_schema"].default.model_fields
            assert "business_id" not in fields

    def test_activities_of_unknown_lead_raise(self, store: InMemoryLeadStore) -> None:
        with pytest.raises(NotFoundError):
            store.list_activities("biz_other", "lead_008")


def test_activity_tool_renders_history(store: InMemoryLeadStore) -> None:
    text = GetLeadActivitiesTool.bind(store, BUSINESS_ID).run(lead_id="lead_008")
    assert "lead_created" in text and "phone_call" in text


def test_metrics_tool(store: InMemoryLeadStore) -> None:
    data = json.loads(GetBusinessMetricsTool.bind(store, BUSINESS_ID).run())
    assert data["total_leads"] == 10
