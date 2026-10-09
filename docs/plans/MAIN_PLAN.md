# AI Lead Management Platform

## Product Vision

Build a customizable AI-powered lead-management platform for businesses that already receive leads.

This is NOT intended to be another generic CRM.

The core engine is reusable, but every business receives a customized setup based on:

* lead sources
* sales process
* industry
* qualification criteria
* custom fields
* existing CRM
* WhatsApp/email/phone integrations
* business rules
* sales-team structure
* automation requirements
* AI instructions

The main promise is:

> Your business already has leads. We make sure you do not lose them.

---

# 1. High-Level Architecture

```text
Website
WhatsApp
Facebook / Instagram
Google Ads
Email
Phone
Existing CRM
Custom API
        ↓
Integration adapters
        ↓
Lead ingestion
        ↓
Normalization
        ↓
Supabase
        ↓
Deterministic business rules
        ↓
CrewAI Flow
        ↓
Specialized AI agents
        ↓
Recommended decision/action
        ↓
Application authorization layer
        ↓
CRM / salesperson / WhatsApp / email
```

Important architecture principle:

```text
Supabase = source of truth

Application services = authority

CrewAI = reasoning + orchestration

Agents = specialists

Tasks = specific pieces of work

Skills = domain/business expertise

Tools = controlled actions

Flows = business processes
```

Never allow an LLM or CrewAI agent to become the source of truth.

---

# 2. Technology Stack

## Backend

* Python 3.12+
* FastAPI
* Pydantic v2
* Supabase Python client for every database call (no ORM, no migration tool)

## AI

* CrewAI
* configurable LLM provider
* structured Pydantic outputs
* business-specific Skills
* CrewAI Flows
* custom CrewAI Tools

Support an LLM abstraction so providers can be replaced.

Possible providers:

* OpenAI
* Anthropic
* Gemini
* local models

## Frontend

* React
* TypeScript
* Vite
* TanStack Query
* React Router
* Tailwind CSS

## Infrastructure

* Docker
* Docker Compose
* Supabase (managed PostgreSQL)
* backend container
* frontend container

---

# 3. Core Application Architecture

Suggested backend structure:

```text
backend/
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── services/
│   ├── integrations/
│   ├── automation/
│   ├── crewai_system/
│   │   ├── agents/
│   │   ├── tasks/
│   │   ├── crews/
│   │   ├── flows/
│   │   ├── tools/
│   │   ├── skills/
│   │   ├── guardrails/
│   │   ├── schemas/
│   │   └── factory/
│   └── main.py
│
├── db/                # the schema: SQL files to paste into the Supabase SQL editor
├── tests/
├── Dockerfile
└── pyproject.toml
```

CrewAI-specific structure:

```text
crewai_system/
├── agents/
│   ├── qualification_agent.py
│   ├── scoring_agent.py
│   ├── conversation_agent.py
│   ├── next_action_agent.py
│   ├── followup_agent.py
│   ├── sales_manager_agent.py
│   └── business_query_agent.py
│
├── tasks/
│   ├── qualify_lead.py
│   ├── analyze_intent.py
│   ├── score_lead.py
│   ├── recommend_action.py
│   ├── generate_followup.py
│   └── summarize_lead.py
│
├── flows/
│   ├── new_lead_flow.py
│   ├── lead_update_flow.py
│   ├── followup_flow.py
│   ├── stale_lead_flow.py
│   ├── inbound_message_flow.py
│   └── sales_assistant_flow.py
│
├── tools/
│   ├── lead_reader.py
│   ├── activity_reader.py
│   ├── business_config_reader.py
│   ├── crm_tool.py
│   ├── email_tool.py
│   ├── whatsapp_tool.py
│   ├── task_tool.py
│   └── notification_tool.py
│
├── skills/
│   ├── lead-qualification/
│   ├── sales-reasoning/
│   ├── follow-up/
│   ├── real-estate/
│   ├── automotive/
│   ├── insurance/
│   └── business-specific/
│
├── guardrails/
│   ├── scoring_guardrail.py
│   ├── messaging_guardrail.py
│   └── action_guardrail.py
│
└── schemas/
    ├── qualification.py
    ├── scoring.py
    ├── next_action.py
    └── followup.py
```

---

# 4. Business Model

Each business must be isolated.

Business fields:

```text
id
name
industry
timezone
configuration
custom_field_definitions
ai_configuration
created_at
updated_at
```

Use JSONB for configuration.

Example:

```json
{
  "lead_scoring": {
    "budget_weight": 0.25,
    "urgency_weight": 0.30,
    "engagement_weight": 0.25,
    "fit_weight": 0.20
  },
  "rules": {
    "high_priority_threshold": 80,
    "critical_threshold": 95
  }
}
```

---

# 5. Lead Model

Core normalized fields:

```text
id
business_id
external_id
source
status
priority

first_name
last_name
email
phone

company_name

notes

lead_score
sentiment

ai_summary
recommended_action

custom_fields
raw_payload

created_at
updated_at
last_contact_at
```

Use JSONB for:

```text
custom_fields
raw_payload
```

Do NOT create dedicated SQL columns for every customer's custom business fields.

---

# 6. Activity Model

Every meaningful event creates an activity.

```text
id
business_id
lead_id
activity_type
channel
description
metadata
created_at
```

Examples:

```text
lead_created
lead_updated

email_sent
email_received

whatsapp_sent
whatsapp_received

phone_call

status_changed
score_changed

proposal_sent
meeting_scheduled

ai_analysis
followup_created
```

Activity history is important context for agents.

---

# 7. Lead Ingestion

Pipeline:

```text
External payload
      ↓
Business adapter
      ↓
Normalize
      ↓
Pydantic validation
      ↓
Deduplicate
      ↓
Store
      ↓
Trigger NewLeadFlow
```

Integration interface:

```python
class LeadAdapter(ABC):
    async def parse(self, payload: dict) -> LeadCreate:
        ...
```

Start with:

```text
JsonLeadAdapter
WebhookLeadAdapter
```

Normalize phone numbers to E.164 at ingestion. Deduplication by phone and WhatsApp matching both depend on it.

Record every inbound webhook event in `ingest_events` before processing it (see Idempotency).

Later:

```text
MetaLeadAdapter
WhatsAppLeadAdapter
HubSpotLeadAdapter
SalesforceLeadAdapter
MondayLeadAdapter
GoogleAdsLeadAdapter
EmailLeadAdapter
```

---

# 8. CrewAI Design Principle

Do NOT create one enormous agent capable of everything.

Agents should have narrow responsibilities.

Bad:

```text
SuperSalesAgent
```

Good:

```text
QualificationAgent
ScoringAgent
ConversationAgent
NextActionAgent
FollowupAgent
SalesManagerAgent
```

CrewAI should be invoked only when reasoning is useful.

Do NOT use CrewAI to perform operations that normal Python handles better.

Examples that should remain deterministic:

```text
database CRUD
authentication
authorization
deduplication
basic filters
mathematical scoring components
webhook validation
business isolation
rate limiting
retry logic
```

---

# 9. CrewAI Skills

Skills represent expertise and instructions.

Skills should NOT directly modify application state.

Suggested skills:

```text
skills/
├── lead-qualification/
│   └── SKILL.md
│
├── lead-scoring/
│   └── SKILL.md
│
├── sales-reasoning/
│   └── SKILL.md
│
├── conversation-analysis/
│   └── SKILL.md
│
├── follow-up-strategy/
│   └── SKILL.md
│
├── objection-handling/
│   └── SKILL.md
│
├── churn-risk/
│   └── SKILL.md
│
├── real-estate/
│   └── SKILL.md
│
├── automotive/
│   └── SKILL.md
│
└── insurance/
    └── SKILL.md
```

---

# 10. Lead Qualification Skill

Purpose:

Teach agents how to determine whether a lead is genuinely qualified.

The skill should explain concepts such as:

```text
buyer intent
budget availability
decision authority
urgency
problem/need
business fit
engagement
purchase timeframe
objections
```

Example logic:

```text
Strong lead:

clear problem
+
clear product fit
+
short purchase timeframe
+
meaningful engagement

Weak lead:

unclear need
+
unknown timeframe
+
low engagement
```

Do NOT hard-code universal qualification logic.

The Skill should combine generic sales principles with business-specific instructions.

---

# 11. Lead Scoring Skill

Teach the Scoring Agent how to evaluate subjective factors.

Examples:

```text
intent strength

urgency

customer fit

engagement quality

purchase readiness

sentiment

decision authority

objection severity
```

The final application score should NOT come entirely from this agent.

Combine:

```text
deterministic_score
+
ai_score
```

Example:

```text
final_score =
    deterministic_score * 0.60
    + ai_score * 0.40
```

Weights must be configurable.

---

# 12. Sales Reasoning Skill

Used by:

```text
NextActionAgent
SalesManagerAgent
```

Teach:

```text
when to call

when to message

when to wait

when to request missing information

when to send pricing

when to send a proposal

when to escalate

when a lead is probably wasting sales time
```

The goal is not merely to say:

```text
High-priority lead.
```

The AI should answer:

```text
Why?

What changed?

What should happen next?

How urgent is it?
```

---

# 13. Conversation Analysis Skill

Used for:

```text
email
WhatsApp
chat
transcripts
CRM notes
```

Extract:

```text
customer intent
questions
requirements
objections
budget
timeline
sentiment
buying signals
commitments
promises
decision maker
next expected action
```

Example:

Customer:

```text
Looks good.

I need to check it with my partner.

Call me on Sunday.
```

Expected structured understanding:

```json
{
  "sentiment": "positive",
  "objection": null,
  "decision_dependency": "partner approval",
  "requested_followup": "Sunday",
  "purchase_intent": "medium_high"
}
```

---

# 14. Follow-Up Strategy Skill

Teach the FollowupAgent how to create useful follow-ups.

Inputs:

```text
lead status
conversation history
last contact
previous objections
business type
customer preferences
salesperson notes
```

Avoid robotic:

```text
Just following up.
```

The agent should understand context.

Example:

```text
Customer said they needed partner approval.

The follow-up should ask whether they had an opportunity
to review the proposal together.
```

---

# 15. Industry Skills

This is where tailor-made business integration becomes powerful.

Example:

```text
skills/real-estate/SKILL.md
```

Could contain:

```text
importance of location
number of rooms
property type
budget
mortgage status
move-in timeframe
investor vs residence
existing property
```

Automotive:

```text
desired vehicle
new / used
trade-in
finance
budget
purchase timeframe
test drive
```

Insurance:

```text
policy type
renewal date
existing provider
premium
coverage requirements
risk type
```

The agents remain reusable.

Their expertise changes based on attached Skills.

---

# 16. Business-Specific Skill

Each customer can receive a generated Skill.

Example:

```text
skills/businesses/acme-solar/SKILL.md
```

Example content:

```text
ACME Solar sells residential solar installations.

Ideal leads:

- own their property
- electricity bill > ₪1,000/month
- live in supported regions
- want installation within 90 days

High priority indicators:

- uploaded electricity bill
- requested ROI calculation
- asked about financing
- scheduled property inspection

Low priority indicators:

- rental property
- outside service region
- researching only
```

This allows customer-specific behavior without forking application code.

---

# 17. CrewAI Tools

Skills tell agents how to reason.

Tools let them interact with the system.

Agents should receive the minimum tools required.

Suggested tools:

```text
GetLeadTool

GetLeadActivitiesTool

GetBusinessConfigurationTool

SearchBusinessLeadsTool

GetSalespersonAvailabilityTool

CreateRecommendationTool

CreateSalesTaskTool

DraftEmailTool

DraftWhatsAppTool

SendEmailTool

SendWhatsAppTool

CRMReadTool

CRMUpdateTool

NotificationTool
```

---

# 18. Tool Security

Prefer separate read and write tools.

Example:

```text
GetLeadTool
```

can read.

It cannot modify.

And:

```text
UpdateLeadTool
```

can modify only specifically allowed fields.

Never create:

```text
ExecuteAnythingTool
```

Never give unrestricted SQL access to an agent.

Never let the agent create arbitrary database queries against production.

Instead expose controlled application-service tools.

---

# 19. Qualification Agent

Role:

```text
Lead Qualification Specialist
```

Goal:

Determine whether the lead matches the customer's sales criteria.

Inputs:

```text
lead
activities
business config
business skill
```

Output:

```python
class QualificationResult(BaseModel):
    qualified: bool
    confidence: float
    intent: str
    urgency: str
    fit: str
    missing_information: list[str]
    positive_signals: list[str]
    negative_signals: list[str]
    summary: str
```

Suggested tools:

```text
GetLeadTool
GetLeadActivitiesTool
GetBusinessConfigurationTool
```

Suggested skills:

```text
lead-qualification
industry skill
business-specific skill
conversation-analysis
```

---

# 20. Scoring Agent

Role:

```text
Lead Intelligence Analyst
```

Goal:

Produce the subjective AI component of lead scoring.

Do NOT calculate the final authoritative score.

Output:

```python
class AIScoreResult(BaseModel):
    intent_score: int
    urgency_score: int
    fit_score: int
    engagement_score: int
    sentiment_score: int
    overall_ai_score: int
    reasons: list[str]
```

Range:

```text
0-100
```

Application combines this result with deterministic scoring.

---

# 21. Conversation Agent

Role:

```text
Customer Conversation Analyst
```

Goal:

Understand inbound customer communication.

Example output:

```python
class ConversationAnalysis(BaseModel):
    intent: str
    sentiment: str
    buying_signals: list[str]
    objections: list[str]
    questions: list[str]
    requested_actions: list[str]
    extracted_fields: dict
    followup_date: datetime | None
```

This agent can update the lead indirectly through application services after validation.

---

# 22. Next Action Agent

Role:

```text
Sales Strategy Advisor
```

Goal:

Determine what should happen next.

Output:

```python
class NextActionRecommendation(BaseModel):
    action: str
    priority: str
    reason: str
    due_at: datetime | None
    requires_human_approval: bool
```

Possible actions:

```text
call
send_whatsapp
send_email
request_information
schedule_demo
send_proposal
wait
nurture
close_lost
escalate_to_manager
```

This agent recommends actions.

It does NOT execute them.

---

# 23. Follow-Up Agent

Role:

```text
Sales Follow-Up Specialist
```

Goal:

Generate personalized follow-up communication.

Output:

```python
class FollowupDraft(BaseModel):
    channel: str
    message: str
    objective: str
    tone: str
```

Possible channels:

```text
WhatsApp
email
SMS
CRM task
```

Initially require human approval before external messaging.

---

# 24. Sales Manager Agent

Role:

```text
AI Sales Manager
```

This agent reasons across multiple leads.

Example questions:

```text
Who should I call today?

Which leads are at risk?

Which deals are likely to close?

Who is waiting on us?

Which salesperson has leads being neglected?

Why did conversion fall this week?
```

This agent should have read-only access to aggregated business data.

Suggested tools:

```text
SearchBusinessLeadsTool
GetLeadActivitiesTool
GetBusinessMetricsTool
```

No unrestricted write access.

---

# 25. Business Query Agent

Role:

```text
Lead Data Assistant
```

Used by the UI AI Assistant.

Example:

```text
User:
Show me strong leads with budgets above ₪50,000
that have not been contacted this week.
```

Architecture:

```text
question
   ↓
BusinessQueryAgent
   ↓
structured search intent
   ↓
application query service
   ↓
PostgreSQL
   ↓
results
   ↓
AI explanation
```

Do NOT send the entire database to the LLM.

---

# 26. CrewAI Tasks

Tasks should be narrowly scoped.

Main tasks:

```text
QualifyLeadTask

AnalyzeConversationTask

ScoreLeadTask

RecommendNextActionTask

GenerateFollowupTask

SummarizeLeadTask

AnalyzeStaleLeadTask

AnalyzePipelineTask
```

---

# 27. QualifyLeadTask

Agent:

```text
QualificationAgent
```

Description:

```text
Evaluate this lead against the business's qualification
criteria and identify intent, fit, urgency, missing information,
positive signals and negative signals.
```

Expected output:

```text
QualificationResult
```

Use structured Pydantic output.

---

# 28. AnalyzeConversationTask

Agent:

```text
ConversationAgent
```

Input:

```text
new message
lead context
recent activity
business rules
```

Output:

```text
ConversationAnalysis
```

This Task should extract structured business information from unstructured conversations.

---

# 29. ScoreLeadTask

Agent:

```text
ScoringAgent
```

Context:

```text
QualificationTask
ConversationAnalysis
Lead history
```

Output:

```text
AIScoreResult
```

The application calculates the final score afterward.

---

# 30. RecommendNextActionTask

Agent:

```text
NextActionAgent
```

Context:

```text
qualification
score
conversation
history
business configuration
```

Output:

```text
NextActionRecommendation
```

---

# 31. GenerateFollowupTask

Agent:

```text
FollowupAgent
```

Input:

```text
lead
conversation history
next action
business tone
channel
```

Output:

```text
FollowupDraft
```

Initially:

```text
human approval required
```

before sending.

---

# 32. Task Guardrails

Every important AI task should have output validation.

Examples:

```text
score must be between 0-100

priority must use valid enum

recommended action must be allowed

message cannot invent pricing

message cannot invent discounts

message cannot claim actions were completed

follow-up date cannot contradict customer request
```

Use Pydantic plus CrewAI guardrails.

---

# 33. CrewAI Flows

Flows should represent actual business processes.

Main flows:

```text
NewLeadFlow

LeadUpdatedFlow

InboundConversationFlow

FollowupFlow

StaleLeadRecoveryFlow

SalesAssistantFlow

PipelineReviewFlow
```

Flows orchestrate agents, tasks, deterministic code and external systems.

---

# 34. NewLeadFlow

This is the most important initial Flow.

```text
Lead arrives
    ↓
Validate payload
    ↓
Normalize
    ↓
Deduplicate
    ↓
Store
    ↓
QualificationAgent
    ↓
ScoringAgent
    ↓
Deterministic scoring
    ↓
Combine score
    ↓
NextActionAgent
    ↓
Route based on priority
```

Routing:

```text
score >= 90
      ↓
critical/hot
      ↓
notify salesperson immediately

70-89
      ↓
qualified
      ↓
create sales task

40-69
      ↓
nurture

<40
      ↓
low priority
```

---

# 35. NewLeadFlow State

Use typed Pydantic Flow state.

Example:

```python
class NewLeadFlowState(BaseModel):
    business_id: UUID
    lead_id: UUID

    qualification: QualificationResult | None = None
    ai_score: AIScoreResult | None = None

    deterministic_score: int | None = None
    final_score: int | None = None

    recommendation: NextActionRecommendation | None = None

    errors: list[str] = []
```

Do not pass uncontrolled dictionaries through Flow state when a model can be used.

---

# 36. NewLeadFlow Concept

Conceptually:

```python
class NewLeadFlow(Flow[NewLeadFlowState]):

    @start()
    def load_context(self):
        ...

    @listen(load_context)
    def qualify(self):
        ...

    @listen(qualify)
    def score(self):
        ...

    @listen(score)
    def calculate_final_score(self):
        ...

    @listen(calculate_final_score)
    def recommend_action(self):
        ...

    @router(recommend_action)
    def route_priority(self):
        ...

    @listen("critical")
    def handle_critical(self):
        ...

    @listen("normal")
    def handle_normal(self):
        ...
```

Keep individual methods small.

---

# 37. InboundConversationFlow

Triggered when a new:

```text
WhatsApp
email
SMS
chat message
call transcript
```

arrives.

Flow:

```text
message arrives
      ↓
identify lead
      ↓
store message
      ↓
ConversationAgent
      ↓
extract new information
      ↓
update validated fields
      ↓
QualificationAgent
      ↓
ScoringAgent
      ↓
recalculate score
      ↓
NextActionAgent
      ↓
route action
```

This allows leads to evolve over time.

---

# 38. FollowupFlow

Triggered when:

```text
recommended follow-up becomes due
```

Flow:

```text
load lead
   ↓
check latest activity
   ↓
verify follow-up still relevant
   ↓
FollowupAgent
   ↓
generate message
   ↓
guardrails
   ↓
approval
   ↓
send
   ↓
record activity
```

Important:

Before sending, check whether the customer responded after the follow-up was scheduled.

Never send outdated automated messages.

---

# 39. StaleLeadRecoveryFlow

Scheduled Flow.

Example:

```text
Find leads with:

status = qualified

AND

last_contact > 5 days
```

For each lead:

```text
analyze history
      ↓
determine whether lead is recoverable
      ↓
generate recovery strategy
      ↓
create salesperson task
```

Do not automatically spam every stale lead.

---

# 40. PipelineReviewFlow

Runs periodically.

Example:

```text
daily
```

or:

```text
every morning
```

Flow:

```text
load active pipeline metrics
      ↓
identify anomalies
      ↓
SalesManagerAgent
      ↓
produce daily priorities
```

Example output:

```text
17 leads need attention.

5 hot leads have not been contacted.

3 proposals have had no response for 4+ days.

2 leads requested calls today.

Tomer Katz should be contacted first.
```

---

# 41. SalesAssistantFlow

Triggered by user question.

Example:

```text
Who should I call today?
```

Flow:

```text
question
   ↓
BusinessQueryAgent
   ↓
determine search requirements
   ↓
query database
   ↓
rank records
   ↓
SalesManagerAgent
   ↓
explain results
```

---

# 42. Human-in-the-Loop

Use human approval for important external actions.

Initially require approval for:

```text
send WhatsApp

send email

send proposal

apply discount

mark deal lost

change high-value opportunity status
```

Approval must happen where the owner already is: the proposed message is sent to the owner on WhatsApp/Telegram
with Approve / Edit / Reject. The dashboard is the fallback, not the main approval surface.

Later, businesses may configure autonomy levels.

Example:

```text
AUTONOMY LEVEL 0

AI recommends only.
```

```text
AUTONOMY LEVEL 1

AI drafts messages.
Human sends.
```

```text
AUTONOMY LEVEL 2

AI sends low-risk follow-ups.
Human approves important actions.
```

```text
AUTONOMY LEVEL 3

AI handles most lead management automatically.
```

This could become an important product feature.

---

# 43. Agent Permissions

Agents should operate according to least privilege.

Example:

```text
QualificationAgent

READ:
lead
activity
business config

WRITE:
nothing
```

```text
ConversationAgent

READ:
lead
activity

PROPOSE:
field extraction
```

```text
FollowupAgent

READ:
lead
activity
business tone

CREATE:
draft only
```

```text
SalesManagerAgent

READ:
business-level analytics

WRITE:
nothing
```

Application services remain responsible for writes.

---

# 44. Crew Organization

Do NOT necessarily run all agents as one Crew.

Prefer small Crews.

Example:

```text
LeadIntelligenceCrew

QualificationAgent
ScoringAgent
NextActionAgent
```

Another:

```text
ConversationCrew

ConversationAgent
FollowupAgent
```

Another:

```text
ManagementCrew

SalesManagerAgent
BusinessQueryAgent
```

Flows can invoke the correct Crew depending on the situation.

---

# 45. Why Flows Should Be Above Crews

Recommended hierarchy:

```text
FastAPI
   ↓
Application Service
   ↓
CrewAI Flow
   ↓
Crew / Agent
   ↓
Task
   ↓
Skills + Tools
```

Flow controls the workflow.

Agents reason.

Tasks define work.

Skills provide expertise.

Tools interact with the application.

This prevents agent logic from controlling the entire platform.

---

# 46. Business-Specific Crew Factory

Different businesses may need different Skills and Tools.

Implement:

```text
BusinessCrewFactory
```

Concept:

```python
crew = crew_factory.create_lead_intelligence_crew(
    business_id=business_id
)
```

Factory loads:

```text
generic skills
+
industry skill
+
business-specific skill
+
business configuration
+
allowed tools
```

Do NOT duplicate agent source code per customer.

---

# 47. Example Business Customization

Customer A:

```text
Real-estate agency
```

Agents use:

```text
lead-qualification
sales-reasoning
real-estate
business/customer-a
```

Customer B:

```text
Car dealership
```

Agents use:

```text
lead-qualification
sales-reasoning
automotive
business/customer-b
```

Same agents.

Different expertise.

---

# 48. Deterministic Scoring

Do not delegate everything to AI.

Example:

```text
Budget known                  +10
Purchase timeframe <30 days   +20
Customer responded            +10
Requested pricing             +15
Proposal requested            +20
No response >7 days           -10
Four ignored followups        -20
```

Then:

```text
deterministic_score = 82
AI_score = 91

final =
82 * 0.6
+
91 * 0.4

= 85.6
```

Final:

```text
86
```

---

# 49. AI Assistant

Create natural-language access.

Examples:

```text
Who should I call today?

Which leads might close this month?

Which leads have we neglected?

Show me leads with strong intent but unknown budget.

Which salesperson has the most overdue leads?

Why did Daniel Cohen's score decrease?

What happened with Tomer Katz?
```

Never expose unrestricted SQL generation directly against production.

Translate natural language into validated search/filter models.

---

# 50. Lead Dashboard

Display:

```text
Total Leads

New Leads

Hot Leads

Qualified Leads

Needs Follow-Up

Waiting for Proposal

Inactive Leads

Average Lead Score
```

Also:

```text
lead source distribution
status distribution
score distribution
recent activity
highest priority leads
```

Outcome metrics (what the customer pays for), shown first:

```text
median time to first response

leads with no response

leads recovered (stale leads that replied after a follow-up)
```

The headline is "leads lost this week", ideally 0.

---

# 51. Lead Detail

Header:

```text
Lead name
Company
Score
Priority
Status
Contact methods
```

AI section:

```text
Summary
Intent
Sentiment
Qualification
Buying signals
Objections
Missing information
Recommended next action
Reasoning
```

Timeline:

```text
10:30 Lead received

10:31 Qualification completed

10:32 Score = 86

11:00 Salesperson called

11:45 Customer replied

12:30 Proposal sent
```

---

# 52. Business Configuration

Business owner should eventually configure:

```text
industry

lead statuses

custom fields

scoring weights

business rules

AI instructions

allowed actions

approval rules

automation level

company tone

working hours

sales territories
```

---

# 53. Custom Fields

Example real estate:

```json
{
  "location": "Tel Aviv",
  "rooms": 4,
  "mortgage_approved": true
}
```

Automotive:

```json
{
  "vehicle_model": "Toyota Corolla",
  "trade_in": true,
  "financing": true
}
```

Do not alter SQL schema for every business.

---

# 54. Multi-Tenancy

Every major table must include:

```text
business_id
```

Repository queries must always be business-scoped.

Never allow:

```text
SELECT * FROM leads
```

without tenant filtering at the application/repository level.

Authentication and membership (implemented):

* Users sign in with Google through Supabase Auth in the browser. The frontend uses supabase-js with the
  publishable key for sign-in only; all data goes through FastAPI.
* FastAPI verifies the Supabase access token against the project's JWKS (`app/core/auth.py`). Every route except
  `/health` requires it.
* The `users` table (`id` = Supabase Auth user id) links each user to exactly one business, with a role.
  Creating a business makes the caller its `owner`.
* Every `/businesses/{business_id}/...` route checks that the caller belongs to that business and answers 404
  otherwise, so other businesses' existence is not revealed. A client-supplied `business_id` is never trusted
  on its own.

Roles (stored; only `owner` is assigned so far, permissions per role are not enforced yet):

```text
owner
manager
sales
admin
```

Not built yet: inviting more users to a business.

---

# 55. API

Implemented endpoints (lead routes are nested under the business, so tenant scope is explicit in the URL):

```text
GET    /api/v1/health                                   (public)
GET    /api/v1/me                                       (signed-in user and their business)

POST   /api/v1/businesses                               (caller becomes owner; one business per user)
GET    /api/v1/businesses/{business_id}
PUT    /api/v1/businesses/{business_id}/settings        (scoring, priority, follow-up, custom fields)

POST   /api/v1/businesses/{business_id}/leads
GET    /api/v1/businesses/{business_id}/leads
GET    /api/v1/businesses/{business_id}/leads/{lead_id}
PATCH  /api/v1/businesses/{business_id}/leads/{lead_id}
POST   /api/v1/businesses/{business_id}/leads/import
POST   /api/v1/businesses/{business_id}/leads/rescore
GET    /api/v1/businesses/{business_id}/leads/{lead_id}/score
GET    /api/v1/businesses/{business_id}/leads/{lead_id}/activities
GET    /api/v1/businesses/{business_id}/dashboard
POST   /api/v1/businesses/{business_id}/leads/{lead_id}/analyze   (runs LeadIntelligenceCrew; LLM calls)
```

Planned:

```text
POST   /api/v1/businesses/{business_id}/ai/query
```

Internal AI endpoints should invoke application services, not agents directly.

---

# 56. CrewAI Observability

Record for every Crew/Flow execution:

```text
flow name

business_id

lead_id

started_at

completed_at

agent

task

LLM model

token usage

latency

result status

errors

guardrail failures
```

Do not log sensitive conversation content unnecessarily.

Trace shape (Logfire): one span per request and one span per Crew/Flow run, with log records inside it, so one
lead's whole processing reads as a single trace. Do not open a span per log record.

This information will be extremely useful when debugging customer-specific behavior.

---

# 57. Cost Management

Do NOT run large LLMs for everything.

Examples:

Small model:

```text
message classification
field extraction
simple sentiment
```

Higher reasoning model:

```text
lead qualification
sales strategy
complex opportunity analysis
```

No LLM:

```text
database filters
date calculations
deduplication
authorization
simple business rules
```

Track token cost per business per run (stored with the run). Each business has a monthly AI budget; when it is
reached, AI runs pause (leads are still saved and scored deterministically) and the owner is notified.

Start with one LLM provider. Add others only when cost or quality forces it.

---

# 58. Failure Handling

Every Flow should handle:

```text
LLM timeout

malformed structured output

integration failure

database error

tool failure

rate limit

invalid customer configuration
```

Never lose the original lead because an AI operation failed.

Example:

```text
Lead saved successfully.

AI analysis failed.

Status:

analysis_pending
```

Retry AI independently.

AI runs never execute inside an API request. A request (or a saved lead) enqueues a job; a worker runs the crew,
retries with backoff, and stores the result. The API returns immediately with `analysis_pending`.

---

# 59. Idempotency

Flows triggered by webhooks must be idempotent.

Example:

Meta sends the same webhook twice.

The system must NOT create:

```text
2 leads

2 messages

2 followups
```

Use:

```text
external_event_id
```

and/or idempotency keys.

Store inbound events in an `ingest_events` table with a unique `(business_id, source, external_event_id)`. A repeat
insert is a no-op, and the event is processed once.

---

# 60. Testing

Use:

```text
pytest
```

Tests should cover:

```text
lead import

normalization

deduplication

tenant isolation

deterministic scoring

custom fields

activities

agent structured outputs

task guardrails

flow routing

business-specific Skills

tool permissions

follow-up approval

failed LLM execution

duplicate webhook

stale lead flow
```

Mock LLM calls.

Do not make tests depend on external providers.

---

# 61. Coding Standards

Use senior-level Python practices.

Requirements:

* Python functions should generally remain under 60 lines.
* Split complex logic into focused functions.
* Use Pydantic BaseModel for external schemas.
* Use dataclasses when appropriate for internal domain models.
* Use typed enums.
* Use async database operations.
* Use dependency injection.
* Use repositories for persistence.
* Use services for business logic.
* Keep FastAPI routes thin.
* Avoid dictionaries when typed models are suitable.
* Never put SQL in CrewAI agents.
* Never put database sessions in prompts.
* Avoid giant classes.
* Use structured logging.
* Use centralized exception handling.
* Use explicit return types.
* Avoid hidden side effects.

---

# 62. Implementation Phases

Order: the core and AI foundation (Phases 1–5), then one channel working end to end with real customers
(Phases 6–7), then breadth (Phases 8–12). Phases 6–7 deliver the main promise ("you do not lose leads"); every
later phase should be justified by what paying customers ask for.

## Phase 1 — Core Platform

Implement:

```text
FastAPI

React

Supabase PostgreSQL

Docker Compose

Supabase client

SQL schema files (db/)

Sign in with Google (Supabase Auth) + token verification in FastAPI

users table: one business per user, membership checked on every business route

Business model

Lead model

Activity model
```

No AI yet.

Status: done. CI runs in GitHub Actions (`.github/workflows/ci.yml`); `tests/platform/test_data_api_lockdown.py`
checks that the publishable key cannot read or write the tables.

---

## Phase 2 — Lead Management

Implement:

```text
JSON import

normalization

deduplication

lead persistence

lead API

dashboard

lead table

lead details

activity timeline
```

Use:

```text
sample_raw_leads.json
```

Status: done. Lead and activity are saved as two requests (not one transaction); the dashboard is computed in
Python (no SQL functions). Not built: webhook idempotency (`ingest_events`), E.164 phone normalization.

---

## Phase 3 — Deterministic Intelligence

Implement:

```text
business configuration

custom fields

scoring rules

priority calculations

follow-up rules
```

Do this before CrewAI.

Status: done. Settings live in the existing `businesses` JSONB columns (`app/schemas/configuration.py`); the rules
are pure functions in `app/intelligence/`. The AI part of the score is, for now, the score an import brings.
Not built: per-role permissions on who may change settings (any member can), automatic rescoring over time
(time-based rules apply on the next write or an explicit rescore), and follow-up actions (Phase 9).

---

# 63. Phase 4 — CrewAI Foundation

Install/configure CrewAI.

Implement:

```text
crewai_system/

Skills

Tools

Pydantic outputs

guardrails
```

Start with only:

```text
QualificationAgent

ScoringAgent

NextActionAgent
```

Status: done in `ai/` (agents, tasks, skills, read-only tools, guardrails, structured outputs, crew factory), tested
with a scripted LLM. Connected to the app by `app/analysis/` (snapshots of one lead, read through `ai.ports`).

---

# 64. Phase 5 — Lead Intelligence Crew

Create:

```text
LeadIntelligenceCrew
```

Tasks:

```text
QualifyLeadTask

ScoreLeadTask

RecommendNextActionTask
```

Test against sample leads.

Verify structured output.

Status: done. `POST .../leads/{lead_id}/analyze` runs the crew on demand and saves its summary, next action and
AI score (an `ai_analysis` activity), blended into the deterministic score. Answer quality is evaluated on the 10
sample leads by `python -m ai.evals` (expected qualification, score band, allowed actions and priority per lead, plus
hot-above-cold score ranking; passes at 80% of cases). It runs against the real model in CI (`llm-eval.yml`:
nightly, manual, and on `ai/**` changes to integration; needs the `OPENAI_API_KEY` secret). First run on
`openai/gpt-5.5`: 10/10, about 30k tokens and 9 LLM requests per lead.

---

# 65. Phase 6 — NewLeadFlow

Prerequisites (production foundations):

```text
background AI jobs: a worker runs crews; POST /analyze enqueues instead of blocking (see Failure Handling)

separate worker image: CrewAI and its dependencies are not in the API image

per-business write lock in the database (Postgres advisory lock or unique constraint + upsert),
replacing the in-process asyncio lock, so more than one backend process is safe

lead + activity written in one transaction (a Supabase RPC), so no lead is saved without its history
```

Implement:

```text
NewLeadFlow
```

Pipeline:

```text
Lead saved
   ↓
Qualification
   ↓
AI scoring
   ↓
Deterministic scoring
   ↓
Final score
   ↓
Next action
   ↓
Priority route
```

The flow runs automatically when a lead is saved (as a background job), not only on demand.

Done when: the AI evaluation set (see Testing) passes against the real model, and cost per lead is recorded.

Status: implemented. Prerequisites: `analysis_jobs` queue with `claim_analysis_job` (SKIP LOCKED, leases, retry with
exponential backoff) and the worker `python -m app.worker` in its own image (the API image has no CrewAI); a
per-business lease in `business_locks` replaces the in-process lock; `save_lead` writes a lead, its activities and
its analysis job in one transaction (db/004_functions.sql). `NewLeadFlow` (`app/analysis/flow.py`) runs on every new
lead (per-business `ai_configuration.auto_analyze`, default on) and on `POST /analyze` (202 + job, polled through
`GET /analysis`). Token usage and, when `AI_PRICE_*_PER_MTOK` are set, dollars are stored per run on the job and the
`ai_analysis` activity. The priority route (hot / warm / cold) is computed and logged; Phase 7 attaches actions to
it. Remaining for "done": a real-model eval run (`llm-eval.yml`) on this branch.

---

# 66. Phase 7 — First Channel End to End

Pull one channel forward from Phase 11 and make the main promise work for one niche:

```text
one inbound channel (WhatsApp or Meta Lead Ads, whichever the first customers use)

webhook ingestion with ingest_events (idempotent)

E.164 phone normalization

NewLeadFlow on every new lead

draft first reply within 60 seconds

owner approval on their phone (Approve / Edit / Reject)

outcome metrics on the dashboard (time to first response, leads with no response)
```

Onboarding: the business starts from an industry preset (skills, custom fields, scoring, approval rules) and only
adjusts it. Target: a new business is live in under 10 minutes, not a custom project.

Choose one niche (real estate, insurance or automotive: whichever customers are reachable) and one market.

Done when: 3–5 businesses use it daily, and at least one pays.

---

# 67. Phase 8 — Conversation Intelligence

Add:

```text
ConversationAgent

AnalyzeConversationTask

InboundConversationFlow
```

Support test messages before integrating WhatsApp/email.

---

# 68. Phase 9 — Follow-Up System

Add:

```text
FollowupAgent

GenerateFollowupTask

FollowupFlow

human approval
```

Messages should be drafts initially.

Do NOT auto-send.

---

# 69. Phase 10 — AI Sales Assistant

Build only when paying customers ask for it.

Add:

```text
BusinessQueryAgent

SalesManagerAgent

SalesAssistantFlow
```

Support:

```text
Who should I call today?

What's happening with this lead?

Which leads need attention?

Which opportunities might close?
```

---

# 70. Phase 11 — External Integrations

The first channel is built in Phase 7. Add the rest in the order customers need them:

```text
WhatsApp

Meta Leads

email

HubSpot

Monday

Salesforce
```

Integrations should use adapters and Tools rather than changing core business logic.

---

# 71. Phase 12 — Business Customization Engine

Implement configuration-driven:

```text
Skills

custom fields

scoring

workflows

AI instructions

integrations

approval rules
```

Create:

```text
BusinessCrewFactory
```

Phase 7 industry presets are the first step; this phase generalizes them into self-serve configuration.

---

# 72. Initial MVP Agents

Do NOT start with seven agents.

Initial MVP:

```text
QualificationAgent

ScoringAgent

NextActionAgent
```

Then add:

```text
ConversationAgent

FollowupAgent
```

Later:

```text
SalesManagerAgent

BusinessQueryAgent
```

---

# 73. Initial MVP Skills

Start with:

```text
lead-qualification

lead-scoring

sales-reasoning
```

Then add one vertical.

Recommended first vertical:

```text
real-estate
```

or whichever real customer is available first.

---

# 74. Initial MVP Tasks

Start with:

```text
QualifyLeadTask

ScoreLeadTask

RecommendNextActionTask
```

---

# 75. Initial MVP Flow

Only implement:

```text
NewLeadFlow
```

Do NOT initially build every Flow listed in this document.

Prove the architecture first.

---

# 76. First CrewAI Milestone

Given:

```text
sample_raw_leads.json
```

The application should be able to produce:

```text
Lead:
Tomer Katz

Qualification:
Highly qualified

AI score:
94

Deterministic score:
98

Final score:
96

Priority:
Critical

Reason:
Immediate requirement, clear business need,
defined budget and active engagement.

Next action:
Schedule technical discovery call immediately.
```

All results must be persisted as structured application data.

AI evaluation set: sample leads (from `sample_raw_leads.json` and, later, anonymized real leads) with the expected
qualification, score range and next action. Run it against the real model on every prompt, skill or model change,
and track the pass rate over time. Scripted-LLM unit tests check the plumbing; the evaluation set checks the answers.

---

# 77. Core Safety Rule

Agents may:

```text
analyze

recommend

classify

extract

summarize

draft
```

Application services may:

```text
validate

authorize

persist

send

delete

change state

execute external actions
```

Use this model:

```text
Agent proposes.

Application validates.

Application executes.
```

---

# 78. Product Differentiator

Do NOT try to compete by saying:

```text
We have AI in our CRM.
```

The product differentiation is:

```text
We build an AI lead-management system around
the way YOUR business already operates.
```

Each company gets:

```text
its own integrations

its own lead schema

its own qualification logic

its own scoring logic

its own AI Skills

its own workflows

its own automation rules
```

while running on the same reusable platform.

Focus before breadth:

```text
one niche and one market first

sell the outcome ("you do not lose leads"), measured on the dashboard

per-business setup starts from an industry preset, so it does not cost a custom project per customer

the first channel is the one the niche lives on (usually WhatsApp)
```

Competitors (HubSpot, GoHighLevel, Pipedrive, Zoho, Salesforce) already ship AI scoring, so scoring alone is not
the product. Response speed and no lost leads in the customer's own channel are.

---

# 79. Final Architecture

```text
                    BUSINESS INPUTS
                          │
          ┌───────────────┼───────────────┐
          │               │               │
       WhatsApp        Website          CRM
          │               │               │
          └───────────────┼───────────────┘
                          ↓
                 Integration Layer
                          ↓
                  Normalization
                          ↓
                     PostgreSQL
                          ↓
                 Application Rules
                          ↓
                    CrewAI Flow
                          ↓
          ┌───────────────┼───────────────┐
          │               │               │
   Qualification       Scoring        Strategy
      Agent             Agent           Agent
          │               │               │
        Skills          Skills          Skills
          │               │               │
        Tools           Tools           Tools
          └───────────────┼───────────────┘
                          ↓
                 Structured Results
                          ↓
               Application Validation
                          ↓
             ┌────────────┼────────────┐
             │            │            │
        Salesperson    WhatsApp       CRM
```

---

# 80. Instructions to Claude Code

Build incrementally.

Do NOT attempt to generate the entire system at once.

For every phase:

1. inspect existing architecture
2. create typed models first
3. implement repository/service boundaries
4. implement functionality
5. write tests
6. run tests
7. run type checking
8. run linting
9. verify the db/ SQL files match app/models
10. verify Docker
11. only then continue

Before writing CrewAI logic, verify whether deterministic Python can solve the requirement more reliably.

Prefer deterministic code whenever possible.

Use CrewAI primarily where semantic understanding, reasoning, business interpretation, or multi-step decision-making provides actual value.

Do not create agents merely because CrewAI supports agents.

Keep the architecture simple until complexity is justified.
