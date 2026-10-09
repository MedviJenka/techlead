---
name: conversation-analysis
description: How to extract structured sales information (intent, sentiment, objections, questions, commitments, decision makers, requested follow-ups, field updates) from emails, WhatsApp, chats, transcripts and CRM notes.
metadata:
  version: "1.0"
---
# Conversation Analysis

Turn unstructured customer communication into structured facts the application can validate.

## Extract

- **intent** — what the customer wants right now, in one sentence.
- **purchase_intent** — none / low / medium / high.
- **sentiment** — positive / neutral / mixed / negative. Politeness is not enthusiasm.
- **buying_signals** — questions about price, availability, contracts, onboarding, start dates.
- **objections** — price, timing, trust, competitor, authority, need.
- **questions** — every explicit question we must answer.
- **requested_actions** — what they asked us to do ("send the contract", "call me Sunday").
- **decision_dependency** — anyone else who must approve ("partner approval", "CFO sign-off").
- **followup_date** — only if the customer gave or clearly implied a time. Resolve relative dates
  ("Sunday", "next week") against the message timestamp and the business timezone. Otherwise null.
- **extracted_fields** — proposed updates (budget, timeframe, rooms, vehicle model...). Use the
  customer's stated value; set confidence below 0.7 when it is implied rather than stated.

## Example

Customer: "Looks good. I need to check it with my partner. Call me on Sunday."

- sentiment: positive · objections: none · decision_dependency: "partner approval"
- requested_actions: ["call on Sunday"] · followup_date: the coming Sunday · purchase_intent: high

## Rules

- Extract only what is in the text. Never fabricate budgets, dates or names.
- You propose field changes; the application decides whether to apply them.
- Do not repeat sensitive personal data unnecessarily.
