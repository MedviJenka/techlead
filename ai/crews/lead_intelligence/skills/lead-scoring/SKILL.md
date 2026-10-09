---
name: lead-scoring
description: How to score the subjective dimensions of a lead (intent, urgency, fit, engagement, sentiment) on 0-100 scales. Produces only the AI component; the application owns the final score.
metadata:
  version: "1.0"
---
# Lead Scoring (AI component)

You produce the **subjective** part of the score. The application blends your `overall_ai_score`
with a deterministic score (budget known, response times, ignored follow-ups...) using
business-configured weights. Do not try to reproduce or override the deterministic part.

## Calibration (applies to every 0-100 dimension)

| Range | Meaning |
|---|---|
| 90-100 | Exceptional, explicit evidence ("we need this now, budget approved") |
| 70-89 | Strong, clear evidence with minor gaps |
| 40-69 | Mixed or partial evidence |
| 20-39 | Weak evidence, mostly unknowns |
| 0-19 | Evidence points the other way |

## Dimensions

- **intent_score** — how strongly they are trying to buy (pricing/proposal/demo requests > general questions).
- **urgency_score** — timeframe pressure. "Immediate" ≈ 90+, "this quarter" ≈ 70, "1-3 months" ≈ 60,
  "6+ months" ≈ 20, unknown ≈ 35.
- **fit_score** — match with the ideal customer profile from the business skill.
- **engagement_score** — responsiveness and depth. Replied and asked questions ≈ 75+; never contacted
  ≈ 40 (neutral, not negative); several ignored attempts ≈ 15.
- **sentiment_score** — 50 is neutral; enthusiasm 75+; frustration or hostility < 30.
- **overall_ai_score** — your holistic judgement. Normally within ±10 of the component average;
  never more than 25 away.

## Rules

- Use the qualification result as context, but score from the raw facts.
- Give at least two concrete `reasons`, each tied to evidence ("Timeframe 'immediate' → urgency 95").
- Never invent facts to justify a score. Unknown data pulls a score toward the middle, not to zero.
