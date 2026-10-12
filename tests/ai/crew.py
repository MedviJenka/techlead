from crewai import Agent
from ai.crews import BusinessCrew
from collections.abc import Sequence
from crewai.project import CrewBase, agent
from tests.ai.schema import ResponseEvaluation
from ai.schemas.lead import latest_lead_message, render_activities
from ai.schemas import ActivitySnapshot, ConversationAnalysis, FollowupDraft, InboundMessage, LeadSnapshot, ModelTier


@CrewBase
class ResponseEvaluatorCrew(BusinessCrew):
    """
    LLM judge for the ConversationCrew's output: grades a response against the same context its author had.

    The judge gets no tools and no memory: everything it may rely on is in the prompt, so each grade is
    reproducible from its inputs.
    """

    @agent
    def response_evaluator(self) -> Agent:
        return self.make_agent("response_evaluator", tier=ModelTier.REASONING, memory=False)

    def evaluate_analysis(
        self,
        lead: LeadSnapshot,
        message: InboundMessage,
        analysis: ConversationAnalysis,
        activities: Sequence[ActivitySnapshot] = (),
    ) -> ResponseEvaluation:
        return self.run_step(self.response_evaluator(), "evaluate_analysis_task", ResponseEvaluation, {
            "channel": message.channel.value,
            "message": message.body,
            "received_at": message.received_at.isoformat(),
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
            "response_json": analysis.model_dump_json(indent=1),
        })

    def evaluate_followup(

        self,
        lead: LeadSnapshot,
        draft: FollowupDraft,
        insights: ConversationAnalysis | None = None,
        activities: Sequence[ActivitySnapshot] = ()

    ) -> ResponseEvaluation:

        lead_message = latest_lead_message(lead, list(activities))
        return self.run_step(self.response_evaluator(), "evaluate_followup_task", ResponseEvaluation, {
            "channel": draft.channel.value,
            "lead_message": lead_message or "None: the lead has not written yet.",
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
            "conversation_insights": insights.model_dump_json(indent=1) if insights else "None available.",
            "response_json": draft.model_dump_json(indent=1),
        })
