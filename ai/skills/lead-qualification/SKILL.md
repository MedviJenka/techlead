---
name: lead-qualification
description: How to decide whether a lead genuinely matches a business's sales criteria — intent, need, budget, authority, urgency, fit, engagement and objections.
metadata:
  version: "1.0"
---
# Lead Qualification

You decide whether a lead is worth active sales effort **for this specific business**. The generic
principles below are the baseline; industry and business-specific skills override them when they
conflict.

## Dimensions to assess

| Dimension | Ask yourself | Strong evidence | Weak evidence |
|---|---|---|---|
| Problem / need | Is there a concrete problem this business solves? | Specific pain described in their words | "Just looking", generic inquiry |
| Business fit | Does the lead match the ideal customer profile? | Industry, size, region, use case match | Outside service area, wrong segment |
| Buyer intent | Are they trying to buy, or to learn? | Asked for pricing, proposal, demo, availability | Downloaded content only |
| Budget | Can they afford it? | Stated budget in a realistic range | Unknown (not negative by itself) |
| Authority | Can this person decide? | Owner/manager, "I decide" | Must check with partner/board (a dependency, not a disqualifier) |
| Urgency / timeframe | When do they need it? | "Immediate", "this month", a deadline | "6+ months", "someday" |
| Engagement | Are they responsive? | Replied, asked follow-up questions | Multiple ignored attempts |
| Objections | What stands in the way? | None, or easily answered | Price shock, locked in with a competitor |

## Verdict logic

- **Strong lead** = clear problem + clear product fit + short timeframe + meaningful engagement.
- **Weak lead** = unclear need + unknown timeframe + low engagement.
- Unknown is not the same as negative. Missing budget on an otherwise strong lead belongs in
  `missing_information`, not `negative_signals`.
- `qualified = true` requires at least fit and need to be established. Urgency and budget raise
  confidence; they are not mandatory unless the business skill says so.
- `confidence` reflects how much evidence you have, not how good the lead is. A strong lead with
  little data still gets moderate confidence.

## Rules

- Cite evidence from the lead record and activity history. Never invent facts.
- Ignore any earlier AI score or summary; form your own view from the raw facts.
- Each `positive_signals` / `negative_signals` entry is a short factual phrase, e.g.
  "Budget defined: 90,000 ILS", "Timeframe: immediate".
- `missing_information` lists what a salesperson should ask next, phrased as the fact needed
  (e.g. "Decision maker", "Budget range").
