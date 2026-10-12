---
name: evaluation-rubric
description: The shared scoring scale, anomaly kinds and severities for grading any AI sales response (analysis, follow-up draft) against the context it was given.
metadata:
  version: "1.0"
---
# Evaluation Rubric

Grade the response against the context it was given, never against what you would have written.

## Criteria (0-10 each)

| Criterion    | 10 means                                                     | 0 means                                         |
|--------------|--------------------------------------------------------------|-------------------------------------------------|
| faithfulness | Every claim traces back to the message, lead record or rules | Invented facts, values, dates or promises       |
| completeness | Nothing the customer said or asked is missing                | Key facts, questions or requests ignored        |
| policy       | Follows every business rule and the platform's limits        | Breaks a rule or claims an action was performed |
| usefulness   | A salesperson can act on it immediately                      | Vague, generic or contradicts itself            |

The skill for the response type may add criteria. Score each one, then set the overall `score` (0-100)
as your judgement of the whole, not an average: one critical defect caps it at 40.

## Anomalies

Report each problem once, with `evidence` quoting the response (or naming the missing fact).

| Kind             | Example                                                          |
|------------------|------------------------------------------------------------------|
| hallucination    | A budget, price, date or name that is nowhere in the context     |
| missed_fact      | The customer asked a question the analysis does not list         |
| wrong_value      | "Sunday" resolved to the wrong date; sentiment opposite the text |
| policy_violation | "I've booked the call", a discount offered, pressure tactics     |
| wrong_language   | Replying in English to a lead who wrote in Hebrew                |
| tone             | Robotic, pushy, or off the business's configured tone            |
| format           | Wrong length for the channel, subject missing on email           |

## Severity

- **critical** — would mislead the customer or corrupt the CRM (invented price, false claim of action).
- **high** — wrong enough that a reviewer must fix it before use.
- **medium** — noticeably weaker but still usable.
- **low** — polish.

## Confidence

`confidence_level` is how sure you are of your own grade (0-1): lower it when the context is thin,
the message is ambiguous, or more than one reading is reasonable.
