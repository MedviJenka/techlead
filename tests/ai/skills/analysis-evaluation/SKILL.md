---
name: analysis-evaluation
description: How to grade a ConversationAnalysis (intent, sentiment, objections, questions, requested actions, decision dependency, follow-up date, extracted fields) against the customer message it was extracted from.
metadata:
  version: "1.0"
---
# Analysis Evaluation

Re-read the message yourself first, then check the analysis field by field.

## Field checks

- **intent** — one sentence that matches what the customer wants now.
- **purchase_intent / sentiment** — consistent with the text. Politeness is not enthusiasm; "looks good,
  call me Sunday" is positive with high intent.
- **objections** — every price, timing, authority, trust, competitor or need objection is listed, and
  none is invented. "I need to check with my partner" is an authority dependency, not a rejection.
- **questions / requested_actions** — every explicit question and request appears.
- **decision_dependency** — set when someone else must approve; null otherwise.
- **followup_date** — present only when the customer gave or clearly implied a time, and resolved
  against the message timestamp. A date the customer never mentioned is a hallucination.
- **extracted_fields** — each value is what the customer stated; implied values carry confidence
  below 0.7. A field the lead record already holds unchanged adds nothing.

## Extra criterion

**calibration** (0-10) — purchase_intent, sentiment and field confidences are neither inflated nor
understated by what the text supports.

## Example

Message: "Looks good. I need to check it with my partner. Call me on Sunday."

- A correct analysis lists decision_dependency "partner approval", requested_actions "call on Sunday"
  and the coming Sunday as followup_date.
- `objections: ["price"]` — hallucination, high.
- `followup_date: null` — missed_fact, high.
- `sentiment: negative` — wrong_value, high.
