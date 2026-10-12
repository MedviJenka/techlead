# Business Model

How the product makes money. This is the commercial model; the `Business` entity (data model) is
`plans/MAIN_PLAN.md` §4.

Status (2026-10-11): pre-revenue. Phase 7 (WhatsApp first reply) is built; no business uses it yet. Every price
below is a starting point to test in the pilot, not market research.

---

## 1. Promise

> Your business already has leads. We make sure you do not lose them.

A lead who writes on WhatsApp gets a reply drafted within a minute. The owner approves it on their own phone (Approve /
Edit / Reject), and nothing reaches the lead without that approval. The dashboard shows what the owner usually cannot
see: median time to first response and the open leads nobody has answered.

## 2. Customer

| | |
|---|---|
| Niche | Real estate (industry preset in `app/presets.py`) |
| Buyer | Independent agent or small agency owner, who is also the user |
| Market | Israel first (`+972`); the market is per business (`configuration.phone_region`) |
| Channel | WhatsApp Cloud API |

Why them: leads arrive on WhatsApp at all hours, the first agent to answer usually gets the viewing, and one closed
deal is a commission in the thousands. A missed lead has a visible price.

## 3. Pricing

Flat monthly price per business with a cap on new leads, priced on the value of a deal, not on our cost.

| Plan | For | Price (to test) | Includes |
|---|---|---|---|
| Pilot | First 3–5 businesses | Free for 30 days, then Solo | Everything, for weekly feedback |
| Solo | One agent | ~$99/month (~₪350) | 1 WhatsApp number, ~300 new leads/month |
| Office | Small agency | ~$249/month (~₪900) | Team seats, higher lead cap |
| Overage | Above the cap | Per extra new lead, or upgrade | Protects margin in a busy month |

Rules:

- Charge from month two. A free pilot that never converts does not test the price.
- Quote the first business $99. Instant yes → quote the next one $149. Everyone pushes back → find out whether it is
  price or value before discounting.
- Office depends on team invites, which are not built yet (see §7).

## 4. Unit economics

### What costs money

| Event | Cost |
|---|---|
| First message from a new phone number | Lead + full AI analysis + first-reply draft: **the only expensive step** |
| Later messages from the same number | Joined to the lead as an activity, no AI call: ~free |
| Owner's approval taps | Free |
| Meta redeliveries | Dropped by `ingest_events`: free |
| WhatsApp template messages (approval to an owner outside the 24-hour window) | Meta fee per message |
| Replies to a lead within 24 hours of their last message | Generally free from Meta |

Cost therefore scales with **new people writing per day**, not message volume. Hundreds of messages a day is
typically 5–30 new leads for an agent (estimate, to measure in the pilot).

### Measured AI usage per new lead

From `analysis_jobs.usage` (2026-10-11, `openai/gpt-5.5` for every agent, `AI_FAST_MODEL` unset):

| | Per lead |
|---|---|
| Requests | 15 |
| Prompt tokens | ~32k, of which ~10k cached |
| Completion tokens | ~5k |
| First-reply draft | Not recorded yet (`.docs/TECH_DEBT.md`) |

```text
cost per lead = (22k × input price + 10k × cached price + 5k × output price) / 1,000,000
```

Dollar cost is stored per job once `AI_PRICE_INPUT_PER_MTOK`, `AI_PRICE_CACHED_INPUT_PER_MTOK` and
`AI_PRICE_OUTPUT_PER_MTOK` are set; they are not set yet.

Illustration only (made-up prices: $5 input, $0.50 cached, $30 output per million tokens): ~$0.27 per lead.
At 30 new leads a day that is ~$8/day, ~$240/month: more than the Solo price. Cost reduction (§5) comes before
quoting anyone.

### Targets

- AI + WhatsApp cost under ~20% of the plan price.
- At Solo ($99, 300 leads): under ~$0.07 per new lead all in.

## 5. Cost levers

In order of expected payoff:

1. **`AI_FAST_MODEL`**: move extraction and classification agents (most of the 15 requests) to a cheap model.
2. **Measure**: set `AI_PRICE_*` so every job records dollars; record the drafting cost too.
3. **Cheaper main model**: re-run the real-model eval (`llm-eval.yml`, 10 cases) with a cheaper `OPENAI_MODEL`;
   switch if it still passes.
4. **Lead gate**: a cheap "is this a lead?" check before the full crew, so suppliers, friends and wrong numbers do
   not each cost an analysis. Per-business `ai_configuration.auto_analyze` already turns analysis off entirely.
5. **Lead cap and overage** in the plan (§3) bound the worst case per business.

## 6. Go to market

1. **Prepare**: deploy, connect the Meta test number, approved approval template, `AI_FAST_MODEL` and `AI_PRICE_*`
   set, a full run on real WhatsApp.
2. **Find 3–5 agents**: personal network first; real estate offices, agent groups.
3. **Onboard together on a call** (~30 minutes): register a dedicated number in our Meta business, connect it in
   Settings → WhatsApp, set the country code, adjust the real-estate preset, send a test lead, approve the first
   reply.
4. **Run 30 days**: weekly check-in, measure the metrics in §8.
5. **Convert**: quote Solo at the end of the pilot.

Phase 7 is done when 3–5 businesses use it daily and at least one pays (`plans/MAIN_PLAN.md` §66).

## 7. Constraints and risks

| Risk | Impact | Mitigation |
|---|---|---|
| One `WHATSAPP_ACCESS_TOKEN` for every number | Customers' numbers must live in our Meta business; no customer-owned WABAs | Fine for the pilot; Embedded Signup before scaling |
| Existing business number | Moving a number to the Cloud API has meant leaving the WhatsApp app | Dedicated new number per customer |
| AI cost per lead | Margin negative at Solo price with the current model | §5 before quoting |
| Owner must approve every reply | Slow owner → slow first response | Opt-in auto-send: an undecided first reply goes out after 5–60 min (never for poor-fit leads); dashboard fallback; measure approval time |
| Onboarding needs us | The owner cannot get a Phone number ID alone | Onboarding call; self-serve later |
| No team invites | Office plan not sellable yet | Build when a pilot agency asks |
| Lead import is JSON only | Agents have spreadsheets | Convert for them; CSV import next |
| Meta business verification | Needed for higher sending limits | Start it before the pilot |

## 8. Metrics

| Metric | Why | Source |
|---|---|---|
| Median time to first response | The promise | Dashboard |
| Open leads with no response | Leads lost before | Dashboard |
| Replies waiting for approval / approval time | Owner is the bottleneck | Dashboard |
| New leads per business per day | Cost driver, cap sizing | `leads` |
| Cost per new lead (AI + WhatsApp) | Margin | `analysis_jobs.cost_usd` once `AI_PRICE_*` is set |
| Daily active businesses | Phase 7 "done" | Logins, approvals |
| Pilot → paid conversion and accepted price | The price | Manual |

## 9. Open questions

- What does answering leads cost an agent today (own time, an assistant, missed leads)?
- How do agents book viewings? Decides whether calendar sync (Google Calendar) is worth building.
- Which cheaper model passes the eval, and what is the real cost per lead then?
- Solo vs Office: how many pilot customers are agencies with a team?
