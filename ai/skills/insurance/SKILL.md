---
name: insurance
description: Insurance lead expertise — policy type, renewal date, existing provider, premium, coverage requirements and risk type.
metadata:
  version: "1.0"
---
# Insurance Leads

## Key qualification facts

- **Policy type** — car, home, health, life, business; route to the right specialist.
- **Renewal date** — the strongest urgency signal; renewal within 30 days means high urgency.
- **Existing provider** — switching intent and the reasons for dissatisfaction.
- **Current premium** — context only; never promise a lower premium.
- **Coverage requirements** — specific needs signal serious intent.
- **Risk type** — high-risk profiles may not fit the business's underwriting appetite.

## Rules

- Never quote premiums, coverage or eligibility — these are regulated, human/underwriter decisions.
- Renewal date unknown → `request_information` is usually the right first step.
