---
name: Techlead
description: AI lead-management workspace for businesses that already receive leads.
colors:
  primary: "#0E7C66"
  primary-hover: "#0A6352"
  on-primary: "#FFFFFF"
  ink: "#14171F"
  ink-muted: "#5B6170"
  ink-subtle: "#8A90A0"
  surface: "#FFFFFF"
  background: "#F6F5F1"
  border: "#E4E2DA"
  ai: "#5B5BD6"
  ai-surface: "#EFEFFD"
  hot: "#E8672A"
  hot-surface: "#FDEEE5"
  success: "#1F9D55"
  warning: "#C98A0B"
  danger: "#C8372D"
typography:
  heading:
    fontFamily: Manrope
    fontWeight: 700
  body:
    fontFamily: Inter
    fontWeight: 400
    fontSize: 14px
  data:
    fontFamily: JetBrains Mono
    fontWeight: 500
rounded:
  sm: 6px
  md: 10px
  lg: 14px
  full: 9999px
spacing:
  unit: 4px
  gutter: 24px
---

# Techlead — UI/UX Design

> Your business already has leads. We make sure you do not lose them.

This file is the design source of truth for the Techlead frontend and the input for the Google Stitch
project. The YAML front matter above is the token set Stitch imports as a design system. The prose
below describes the experience, the components and every screen. Each screen has a prompt you can
paste into Stitch.

## 1. Product and users

Techlead is an AI-assisted lead workspace, not a generic CRM. Its main user is a **business owner or
sales lead** at a small or mid-size company (solar, real estate, clinics, agencies). They spend the
day switching between WhatsApp, email and phone. They open Techlead to answer three questions fast:

1. **Who do I contact right now?** (hot leads, overdue follow-ups)
2. **What happened with this person?** (one lead's full story)
3. **Is anything slipping?** (inactive leads, unanswered sources)

Secondary user: a **salesperson** who works the lead list and approves AI-drafted follow-ups.

## 2. Design principles

1. **Action first, data second.** Every screen leads with the next action ("Call Dana, score 91,
   no contact in 3 days"), then the supporting numbers.
2. **AI is advice, never fact.** Anything an agent produced (summary, score reasoning, recommended
   action, drafted message) sits on the violet `ai-surface` with a small "AI" sparkle tag. Data
   from the source system or a person never uses violet. People can always see where a claim came from.
3. **Humans approve outbound actions.** Drafted messages show an Approve / Edit / Discard bar. The
   AI never sends anything silently.
4. **Calm density.** This is a work tool used all day: compact tables, 14px body text, generous
   whitespace between sections and little inside them. No decorative gradients and no hero
   illustrations inside the app.
5. **Heat is the only loud colour.** Orange `hot` marks high or critical priority and urgent
   follow-ups. Everything else stays neutral, so the eye goes to what needs attention.

## 3. Visual language

| Token | Value | Use |
|---|---|---|
| `background` | `#F6F5F1` warm paper | App canvas |
| `surface` | `#FFFFFF` | Cards, tables, panels |
| `ink` / `ink-muted` | `#14171F` / `#5B6170` | Text |
| `primary` | `#0E7C66` deep teal | Primary buttons, links, active nav, focus rings |
| `hot` | `#E8672A` ember | Hot leads, critical priority, overdue |
| `ai` / `ai-surface` | `#5B5BD6` / `#EFEFFD` | AI-generated content only |
| `success` / `warning` / `danger` | green / amber / red | Status and system feedback |

- **Type:** Manrope 700 for headings (page title 24px, section 16px). Inter 14px for body and
  tables. JetBrains Mono for scores, counts, IDs and timestamps, so the numbers line up.
- **Shape:** 10px radius for cards, 6px for inputs and buttons, full pills for status chips.
- **Elevation:** a 1px `border` line on cards. A shadow appears only on popovers, drawers and modals.
- **Icons:** Material Symbols Rounded, 20px, outlined weight.
- **Dark mode:** canvas `#0F1115`, surface `#171A21`, borders `#262A33`. Primary lightens to
  `#2BB596`, AI to `#8B8BF0`.

## 4. App shell

- **Left sidebar (240px, collapsible to 64px):** logo "Techlead", business switcher (name and
  industry), then nav: Dashboard, Leads, Follow-ups (badge with count waiting for approval),
  Assistant, Settings. The bottom of the sidebar shows an API health dot ("API online") and the
  user's avatar, email and sign-out.
- **Top bar (56px):** breadcrumb, global search ("Search leads by name, email, phone, company",
  `/` shortcut), an "Import leads" button and an "Ask AI" button that opens the assistant drawer.
- **Content:** max width 1280px, 24px gutter.
- **Mobile (<768px):** the sidebar becomes a bottom tab bar (Dashboard, Leads, Follow-ups,
  Assistant), tables become card lists, and the lead detail becomes a single column.

## 5. Core components

- **KPI tile:** label (ink-muted, 13px), value (Mono 28px), delta or hint line. The Hot tile uses an
  ember left accent. Each tile links to the lead list with that filter applied.
- **Lead row:** avatar initials, name and company, source chip, status chip, priority flag,
  score meter, last contact (relative time, turns ember after 7 days), row actions (call, email,
  open).
- **Score meter:** a Mono number from 0 to 100 with a 4px bar. 0–49 neutral, 50–79 teal, 80+ ember.
- **Status chip:** pill with a dot (New, Contacted, Qualified, Proposal, Won, Lost, Inactive).
- **Priority flag:** Low / Medium / High / Critical. High and Critical use ember.
- **AI card:** `ai-surface` background, a sparkle "AI" tag, a "Why?" disclosure that shows the
  reasoning, and a timestamp that says when the analysis was generated.
- **Timeline item:** time (Mono), channel icon (call, WhatsApp, email, system, AI), description and
  a collapsible metadata block.
- **Approval bar:** drafted message preview, then Approve & send (primary), Edit, Discard.
- **Empty state:** one sentence, one primary action (for example "No leads yet. Import a JSON file
  to get started.").
- **Feedback:** inline `role="alert"` errors under the field or section, skeleton loaders instead of
  "Loading…" text, and toasts for saved changes.

## 6. Screens

The screens map to the routes in `frontend/src/main.tsx`, plus the screens planned in
MAIN_PLAN §49–52.

### 6.1 Sign in — `/` (signed out)
Split layout. On the left, the promise headline "Your business already has leads. We make sure you
do not lose them." with three short value bullets (Never miss a hot lead · AI-drafted follow-ups
you approve · Every lead's story in one timeline). On the right, a card with a "Continue with
Google" button (Supabase Google OAuth) and small terms text.

**Stitch prompt:** Desktop sign-in page for "Techlead", an AI lead-management tool. Split layout on
a warm off-white background. Left half: headline "Your business already has leads. We make sure
you do not lose them.", three value bullets with teal icons, and a subtle preview of a lead card
with an orange "Hot · 91" score. Right half: a white card with the Techlead wordmark, "Sign in to
your workspace", one "Continue with Google" button and small terms text. Calm, professional, no
stock photos.

### 6.2 Create your business — `/` (signed in, no business)
A focused onboarding card, step 1 of 1: Business name, Slug (auto-filled from the name, shown as
`techlead.app/acme-solar`), Industry (select with common options plus free text), Timezone
(auto-detected select). Primary button "Create business". A side note says "You'll be the owner.
You can invite your team later."

### 6.3 Dashboard — `/businesses/:id`
- Header: business name, industry · timezone, date range and "View all leads".
- **"Today" action strip (top):** up to three AI-ranked cards, each "Call Dana Levi · score 91 · no
  contact for 3 days" with a call or WhatsApp button.
- KPI row: Total, New, Hot, Qualified, Needs follow-up, Waiting for proposal, Inactive, Avg score.
  Each tile has a one-line definition in a tooltip (Hot = high or critical priority, and so on).
- Three distribution cards: By source (horizontal bars), By status (stacked bar), By score
  (histogram in 0–49 / 50–79 / 80–100 buckets).
- Two columns: **Top open leads** table (8 rows) and **Recent activity** feed.

### 6.4 Leads — `/businesses/:id/leads`
- Toolbar: search, filter chips for Status, Source, Priority and Score range, saved views ("Hot",
  "Needs follow-up", "Inactive"), a column toggle and an "Import" button.
- Lead table with sortable columns, a sticky header, multi-select with bulk actions (set status,
  set priority, export) and pagination ("1–50 of 1,284").
- **Import drawer:** drop zone for `.json` (up to 10 MB, 1,000 records), a sample-format link,
  progress, and then a result summary in four counters (Created / Updated / Skipped / Failed) and a
  table of failed records showing the field path and the error.

### 6.5 Lead detail — `/businesses/:id/leads/:leadId`
- **Header:** name, company, score meter, priority flag, status chip (editable dropdown),
  contact buttons (Call, WhatsApp, Email, each disabled when that contact method is missing).
- **Left column (2/3):** AI analysis card (Summary, Intent, Sentiment, Qualification, Buying
  signals, Objections, Missing information, Recommended next action, with a "Why?" reasoning
  disclosure), then the Activity timeline with a composer at the top ("Log a call, note or
  message").
- **Right column (1/3):** Details (email, phone, source, external ID, created, last contact), an
  editable Notes field, Custom fields shown as a key/value list rather than raw JSON, and a "Pending
  follow-up" approval card when a draft exists.

### 6.6 Follow-ups (approval queue) — planned
An inbox of AI-drafted follow-ups that wait for a person. On the left, a list of drafts (lead,
channel, reason, age). On the right, a preview with the editable message, the lead's context
snippet and the approval bar. Filters: channel and urgency.

### 6.7 AI Assistant — planned (MAIN_PLAN §49)
A chat panel, as a full page and as a right-hand drawer. It opens with suggested prompts: "Who
should I call today?", "Which leads have we neglected?", "Show leads with strong intent but unknown
budget", "Why did Daniel Cohen's score drop?". Answers show a short sentence, then a structured
result (an inline lead table or a lead card) and a "Filters applied" chip row, so the user can see
how the answer was produced. Never show raw SQL.

### 6.8 Business settings — planned (MAIN_PLAN §52)
A tabbed settings page: General (name, industry, timezone, working hours), Pipeline (lead statuses,
drag to reorder), Custom fields, Scoring (weight sliders for budget, urgency, engagement and fit
that must total 100%, plus hot and critical thresholds), AI (tone, language, autonomy level
slider, allowed actions, actions that need approval, extra instructions) and Team.

## 7. Accessibility and states

- WCAG AA contrast. Ember on white is used for icons and bars only; ember text sits on `hot-surface`.
- Every icon button has an `aria-label`. Status changes use `role="status"` and errors use
  `role="alert"`, as the current code already does.
- Full keyboard paths: `/` focuses search, `j`/`k` move through table rows, `Enter` opens a lead.
- Every data view designs four states: loading (skeleton), empty, error (message and retry) and
  populated.

## 8. Mapping to code

- Tailwind tokens: add the colours above to `@theme` in the Tailwind v4 CSS. Replace `slate-900`
  buttons with `primary` and `blue-50` analysis boxes with `ai-surface`.
- Shared classes in `frontend/src/components/leadDisplay.ts` (`inputClass`, `buttonClass`) become
  components: `Button`, `Input`, `Chip`, `ScoreMeter`, `AiCard`.
- `Layout.tsx` changes from a top header to the sidebar shell in §4. `HealthBadge` moves to the
  sidebar footer.
