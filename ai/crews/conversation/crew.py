from collections.abc import Sequence
from crewai import Agent
from crewai.project import CrewBase, agent
from ai.crews.base import ContextualCrew, task_result
from ai.guardrails import make_messaging_guardrail
from ai.schemas import (
    ActivitySnapshot,
    Channel,
    ConversationAnalysis,
    FollowupDraft,
    InboundMessage,
    LeadSnapshot,
    NextActionRecommendation,
)
from ai.schemas.lead import render_activities


@CrewBase
class ConversationCrew(ContextualCrew):

    """Inbound message understanding and follow-up drafting (MAIN_PLAN §44).

    The two steps are separate kickoffs so Flows can run either alone: InboundConversationFlow
    analyzes, FollowupFlow drafts, and the Flow decides what happens in between.
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def conversation_agent(self) -> Agent:
        return self.build_agent("conversation_agent")

    @agent
    def followup_agent(self) -> Agent:
        return self.build_agent("followup_agent")

    def analyze_message(
        self,
        lead: LeadSnapshot,
        message: InboundMessage,
        activities: Sequence[ActivitySnapshot] = (),
    ) -> ConversationAnalysis:
        task = self.build_task("analyze_conversation_task", ConversationAnalysis)
        output = self.run([self.conversation_agent()], [task], {
            "channel": message.channel.value,
            "message": message.body,
            "received_at": message.received_at.isoformat(),
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
        })
        return task_result(output, ConversationAnalysis)

    def draft_followup(
        self,
        lead: LeadSnapshot,
        channel: Channel,
        recommendation: NextActionRecommendation | None = None,
        insights: ConversationAnalysis | None = None,
        activities: Sequence[ActivitySnapshot] = (),
    ) -> FollowupDraft:
        task = self.build_task("generate_followup_task", FollowupDraft, [make_messaging_guardrail(self.business, lead)])
        output = self.run([self.followup_agent()], [task], {
            "channel": channel.value,
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
            "next_action": recommendation.model_dump_json(indent=1) if recommendation else "None provided.",
            "conversation_insights": insights.model_dump_json(indent=1) if insights else "None available.",
        })
        return task_result(output, FollowupDraft)
