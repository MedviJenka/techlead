---
name: sales-reasoning
description: How to choose the next sales action for a lead — when to call, message, wait, request information, send pricing or a proposal, escalate, or stop investing time.
metadata:
  version: "1.0"
---
# Sales Reasoning

Every recommendation must answer four questions: **Why? What changed? What should happen next?
How urgent is it?** "High-priority lead" on its own is never an acceptable answer.

## Choosing the action

| Situation | Typical action |
|---|---|
| Hot, qualified, not yet contacted, or asked to talk | `call` (fast human contact wins) |
| Qualified, clear B2B use case, ready to see the product | `schedule_demo` |
| Needs and budget known, asked for terms | `send_proposal` |
| Promising but key facts missing (budget, decision maker, timeframe) | `request_information` |
| Prefers a written channel, low-stakes nudge | `send_whatsapp` / `send_email` (respect `preferred_channel`) |
| Customer asked us to come back later | `wait` with `due_at` = their requested time |
| Early research, long timeframe | `nurture` |
| Repeated ignored attempts, no fit, or explicit "not interested" | `close_lost` (requires approval) |
| High-value deal at risk, unhappy customer, or beyond the salesperson's authority | `escalate_to_manager` |

## Priority and timing

- `critical`: act within the hour (immediate need + strong fit + engaged). `due_at` ≈ now.
- `high`: same business day. `medium`: within 2-3 days. `low`: this week or later.
- Respect the business's working hours and timezone when proposing `due_at`.
- If the customer named a time ("call me Sunday"), that wins over generic timing rules.

## Guardrails on your reasoning

- Recommend only actions in the business's allowed list; mark approval-required actions
  `requires_human_approval: true`.
- You recommend; you never claim to have done anything.
- A lead is "probably wasting sales time" only with evidence (no fit, no reply after 4+ attempts,
  explicit refusal) — not merely because data is missing.
- `talking_points` are short, specific prompts for the salesperson (what to confirm, what to show).
