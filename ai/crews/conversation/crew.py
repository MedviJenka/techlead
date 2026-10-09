from collections.abc import Sequence

from crewai import Agent
from crewai.project import CrewBase, agent

from ai.crews.base import BusinessCrew
from ai.guardrails import make_messaging_guardrail
from ai.schemas import (
    ActivitySnapshot,
    Channel,
    ConversationAnalysis,
    FollowupDraft,
    InboundMessage,
    LeadSnapshot,
    ModelTier,
    NextActionRecommendation,
)
from ai.schemas.lead import render_activities
from ai.tools import GetBusinessConfigurationTool, GetLeadActivitiesTool, GetLeadTool


@CrewBase
class ConversationCrew(BusinessCrew):
    """
    Inbound message understanding and follow-up drafting (MAIN_PLAN §44).

    Two independent steps, so a Flow can run either alone and decide what happens in between.
    """

    @agent
    def conversation_agent(self) -> Agent:
        return self.make_agent(
            "conversation_agent",
            tier=ModelTier.FAST,
            tools=[GetLeadTool, GetLeadActivitiesTool],
        )

    @agent
    def followup_agent(self) -> Agent:
        return self.make_agent(
            "followup_agent",
            tier=ModelTier.REASONING,
            tools=[GetLeadActivitiesTool, GetBusinessConfigurationTool],
        )

    def analyze_message(
        self, lead: LeadSnapshot, message: InboundMessage, activities: Sequence[ActivitySnapshot] = ()
    ) -> ConversationAnalysis:
        return self.run_step(self.conversation_agent(), "analyze_conversation_task", ConversationAnalysis, {
            "channel": message.channel.value,
            "message": message.body,
            "received_at": message.received_at.isoformat(),
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
        })

    def draft_followup(
        self,
        lead: LeadSnapshot,
        channel: Channel,
        recommendation: NextActionRecommendation | None = None,
        insights: ConversationAnalysis | None = None,
        activities: Sequence[ActivitySnapshot] = (),
    ) -> FollowupDraft:
        inputs = {
            "channel": channel.value,
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
            "next_action": recommendation.model_dump_json(indent=1) if recommendation else "None provided.",
            "conversation_insights": insights.model_dump_json(indent=1) if insights else "None available.",
        }
        guardrail = make_messaging_guardrail(self.business, lead)
        return self.run_step(self.followup_agent(), "generate_followup_task", FollowupDraft, inputs, [guardrail])
