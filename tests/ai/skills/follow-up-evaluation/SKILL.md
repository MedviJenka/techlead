---
name: follow-up-evaluation
description: How to grade a FollowupDraft (WhatsApp, email, SMS, CRM task) for faithfulness, policy, personalization, language, tone and channel format.
metadata:
  version: "1.0"
---
# Follow-Up Evaluation

A good draft proves the writer remembers the conversation and moves it one concrete step forward.

## Critical failures

- A price, amount, discount, availability, deadline or feature that is not in the context.
- A claim that something was already done ("I've booked", "we have sent the contract").
- `requires_human_approval` set to false.
- Pressure tactics or false urgency.

## Extra criteria (0-10 each)

- **personalization** — references something specific: the lead's need, last question, or what they
  said they would do. "Just following up" / "Checking in" with no content scores 0-2.
- **objective** — one clear objective, matching the draft's `objective` field and the recommended
  next action when one was given.
- **call_to_action** — ends with one easy step (a yes/no question or two time options).
- **channel_fit** — WhatsApp 2-4 short sentences; email has a subject and short paragraphs; SMS
  under 320 characters; CRM task is an instruction for the salesperson. `channel` matches the request.
- **language_and_tone** — written in the language of the lead's latest message (the business's
  default only when the lead has not written), in the business's configured tone.

## Objections

When the lead raised an objection, check the draft answers it honestly:

| Objection | Good draft                                                    | Anomaly                                  |
|-----------|---------------------------------------------------------------|------------------------------------------|
| Price     | Acknowledges, reframes around value, offers to walk through   | Any new number or discount (critical)    |
| Timing    | Agrees a concrete time to reconnect                           | Pushes for now anyway (tone, medium)     |
| Authority | Offers material or a joint call with the decision maker       | Ignores the partner/manager (missed_fact)|
| Trust     | Offers references the business actually has                   | Invented testimonials (hallucination)    |
| Competitor| Finds the gap, never disparages                               | Disparages the competitor (tone, high)   |
