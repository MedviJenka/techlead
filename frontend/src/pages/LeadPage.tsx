import { motion } from 'motion/react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'

import { useActivities, useAnalysisState, useAnalyze, useLead, useLeadMutation, useScore } from '../api/leads'
import { useLeadReplies } from '../api/replies'
import type { LeadDetail } from '../api/types'
import { Pagination } from '../components/Leads'
import { ReplyDraftCard } from '../components/Replies'
import { daysSince, dueLabel, FOLLOW_UP_REASON, inputClass, leadName, relativeTime, titleCase } from '../components/leadDisplay'
import { AiCard, Avatar, Button, Card, CardHeader, EmptyState, ErrorState, Icon, PriorityFlag, Skeleton, SourceChip, Stagger, StatusChip, Toast } from '../components/ui'
import { fadeUp, scoreTone, spring } from '../components/motion'

function ContactTile({ href, icon, label, external }: { href: string | null; icon: string; label: string; external?: boolean }) {
  const base = 'flex flex-1 flex-col items-center gap-1 rounded-md border px-4 py-2.5 text-xs font-medium'
  if (!href)
    return (
      <span className={`${base} cursor-not-allowed border-line text-ink-subtle opacity-50`} title={`No ${label.toLowerCase()} details`} aria-disabled="true">
        <Icon name={icon} />
        {label}
      </span>
    )
  return (
    <motion.a
      href={href}
      target={external ? '_blank' : undefined}
      rel={external ? 'noreferrer' : undefined}
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.95 }}
      transition={spring}
      className={`${base} border-line bg-surface text-ink transition-colors hover:border-primary/40 hover:bg-primary-soft hover:text-primary`}
    >
      <Icon name={icon} />
      {label}
    </motion.a>
  )
}

function LeadHeader({ lead }: { lead: LeadDetail }) {
  const name = leadName(lead)
  const score = lead.lead_score
  const tone = score == null ? null : scoreTone(score)
  const phone = lead.phone?.replace(/[^\d+]/g, '') ?? null
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start gap-5 p-5">
        <motion.div initial={{ scale: 0.6, rotate: -10 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: 'spring', stiffness: 260, damping: 15 }}>
          <Avatar name={name} size="lg" hot={(score ?? 0) >= 80} />
        </motion.div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">{name}</h1>
            <StatusChip status={lead.status} />
            <PriorityFlag priority={lead.priority} />
          </div>
          <p className="mt-0.5 text-ink-muted">{[lead.company_name, lead.email].filter(Boolean).join(' · ') || '—'}</p>
          {score != null && tone && (
            <div className="mt-4 max-w-md">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-ink-muted">Lead score</span>
                <span className={`font-mono text-lg font-medium ${tone.text}`}>
                  {score}
                  <span className="text-xs text-ink-subtle"> / 100</span>
                </span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-line">
                <motion.div
                  className={`h-full rounded-full ${tone.bar}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${score}%` }}
                  transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
                />
              </div>
            </div>
          )}
        </div>
        <div className="flex w-full gap-2 sm:w-auto">
          <ContactTile href={phone && `tel:${phone}`} icon="call" label="Call" />
          <ContactTile href={phone && `https://wa.me/${phone.replace(/\D/g, '')}`} icon="chat" label="WhatsApp" external />
          <ContactTile href={lead.email && `mailto:${lead.email}`} icon="mail" label="Email" />
        </div>
      </div>
    </Card>
  )
}

function Signals({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items.length) return null
  return (
    <div className="mt-3">
      <p className="font-mono text-[11px] font-medium tracking-wide text-ink-subtle uppercase">{title}</p>
      <ul className="mt-1 space-y-0.5 text-[13px]">
        {items.map((item) => (
          <li key={item} className="flex gap-1.5">
            <Icon name="chevron_right" className={`text-base! ${tone}`} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Analysis({ businessId, lead }: { businessId: string; lead: LeadDetail }) {
  const analyze = useAnalyze(businessId, lead.id)
  const state = useAnalysisState(businessId, lead.id)
  const job = state.data?.job
  const result = state.data?.result
  const working = analyze.isPending || job?.status === 'pending' || job?.status === 'running'
  const failed = job?.status === 'failed' && !working
  const hasAnalysis = Boolean(result || lead.ai_summary || lead.recommended_action || lead.sentiment)
  return (
    <AiCard
      title="Lead analysis"
      meta={
        <Button
          type="button"
          variant="ai"
          size="sm"
          icon={working ? 'progress_activity' : 'auto_awesome'}
          disabled={working}
          onClick={() => analyze.mutate({}, { onSuccess: () => void state.refetch() })}
        >
          {working ? (job?.status === 'running' ? 'Analyzing…' : 'Queued…') : hasAnalysis ? 'Analyze again' : 'Analyze with AI'}
        </Button>
      }
      why={
        <>
          AI agents read this lead and its timeline, then qualify it, score it and suggest a next action. Their score is blended into the rules score (see
          “Why this score”); the priority stays rule-based. Every suggestion is advice: nothing is sent or changed in your CRM.
        </>
      }
    >
      {analyze.isError && <ErrorState message={analyze.error.message} />}
      {failed && <ErrorState message={`AI analysis failed after ${job.attempts} attempts. Try again later.`} />}
      {working && job && job.attempts > 0 && job.last_error && (
        <p className="mb-2 text-[13px] text-warning">Retrying (attempt {job.attempts + 1} of {job.max_attempts})…</p>
      )}
      {!hasAnalysis && !analyze.isError && !working && (
        <p className="text-ink-muted">No analysis yet. New leads are analysed automatically; it uses your AI provider.</p>
      )}
      {!hasAnalysis && working && <p className="text-ink-muted">The AI is reading this lead. This usually takes under a minute.</p>}
      {(result?.qualification.summary ?? lead.ai_summary) && <p className="leading-relaxed">{result?.qualification.summary ?? lead.ai_summary}</p>}
      {result && (
        <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[11px]">
          {[
            result.qualification.qualified ? 'Qualified' : 'Not qualified',
            `Confidence ${Math.round(result.qualification.confidence * 100)}%`,
            `Intent ${result.qualification.intent}`,
            `Urgency ${result.qualification.urgency}`,
            `Fit ${result.qualification.fit}`,
            `AI score ${result.ai_score.overall_ai_score}`,
          ].map((label) => (
            <span key={label} className="rounded-sm border border-ai/20 bg-surface/70 px-2 py-1">
              {label}
            </span>
          ))}
        </div>
      )}
      {!result && lead.sentiment && (
        <span className="mt-3 inline-flex rounded-sm border border-ai/20 bg-surface/70 px-2 py-1 font-mono text-[11px]">
          Sentiment: <span className="ml-1 font-semibold text-ai">{titleCase(lead.sentiment)}</span>
        </span>
      )}
      {result && (
        <>
          <Signals title="Positive signals" items={result.qualification.positive_signals} tone="text-success" />
          <Signals title="Concerns" items={result.qualification.negative_signals} tone="text-danger" />
          <Signals title="Still unknown" items={result.qualification.missing_information} tone="text-ink-subtle" />
        </>
      )}
      {(result?.recommendation.action ?? lead.recommended_action) && (
        <div className="mt-4 rounded-md border border-ai/25 bg-surface/80 p-3.5">
          <p className="flex items-center gap-1.5 font-mono text-[11px] font-medium tracking-wide text-ai uppercase">
            <Icon name="target" className="text-base!" />
            Recommended next action
            {result?.recommendation.requires_human_approval && <span className="ml-auto text-warning normal-case">needs approval</span>}
          </p>
          <p className="mt-1.5 font-medium">{titleCase(result?.recommendation.action ?? lead.recommended_action ?? '')}</p>
          {result && <p className="mt-1 text-[13px] text-ink-muted">{result.recommendation.reason}</p>}
          {result && <Signals title="Talking points" items={result.recommendation.talking_points} tone="text-ai" />}
        </div>
      )}
    </AiCard>
  )
}

function ScoreCard({ businessId, lead }: { businessId: string; lead: LeadDetail }) {
  const score = useScore(businessId, lead.id)
  const data = score.data
  return (
    <Card>
      <CardHeader
        title="Why this score"
        icon="calculate"
        action={data ? <span className="font-mono text-[11px] text-ink-subtle">now: {data.final} / 100</span> : undefined}
      />
      <div className="px-5 py-4 text-[13px]">
        {score.isPending && <Skeleton className="h-24" />}
        {score.isError && <ErrorState message={score.error.message} onRetry={() => void score.refetch()} />}
        {data && (
          <>
            <ul className="divide-y divide-line">
              <li className="flex justify-between py-1.5 text-ink-muted">
                <span>Starting score</span>
                <span className="font-mono">{data.base}</span>
              </li>
              {data.matched.map((rule) => (
                <li key={rule.id} className="flex justify-between py-1.5">
                  <span>{rule.label}</span>
                  <span className={`font-mono ${rule.points < 0 ? 'text-danger' : 'text-success'}`}>
                    {rule.points > 0 ? '+' : ''}
                    {rule.points}
                  </span>
                </li>
              ))}
              <li className="flex justify-between py-1.5 font-semibold">
                <span>Rules score</span>
                <span className="font-mono">{data.deterministic}</span>
              </li>
            </ul>
            {data.ai != null && (
              <p className="mt-3 rounded-sm bg-canvas px-3 py-2 text-xs text-ink-muted">
                Blended with the AI score {data.ai}: {data.deterministic} × {(1 - data.ai_weight).toFixed(1)} + {data.ai} ×{' '}
                {data.ai_weight.toFixed(1)} = <span className="font-mono font-semibold text-ink">{data.final}</span>
              </p>
            )}
            {lead.lead_score !== data.final && (
              <p className="mt-3 text-xs text-ink-subtle">
                The saved score ({lead.lead_score ?? '—'}) updates on the next change to this lead, or when the business rescores its leads.
              </p>
            )}
          </>
        )}
      </div>
    </Card>
  )
}

const CHANNEL_ICON: Record<string, string> = {
  call: 'call',
  phone: 'call',
  whatsapp: 'chat',
  email: 'mail',
  sms: 'sms',
  note: 'sticky_note_2',
  status_change: 'swap_horiz',
  import: 'upload',
  ai: 'auto_awesome',
}

function Timeline({ businessId, leadId }: { businessId: string; leadId: string }) {
  const [offset, setOffset] = useState(0)
  const activities = useActivities(businessId, leadId, offset)
  return (
    <Card>
      <CardHeader
        title="Activity timeline"
        icon="timeline"
        action={activities.data ? <span className="font-mono text-[11px] text-ink-subtle">{activities.data.total} events</span> : undefined}
      />
      <div className="px-5 py-4">
        {activities.isPending && (
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="size-7 rounded-full" />
                <Skeleton className="h-10 flex-1" />
              </div>
            ))}
          </div>
        )}
        {activities.isError && <ErrorState message={activities.error.message} onRetry={() => void activities.refetch()} />}
        {activities.data && !activities.data.total && <EmptyState icon="history" title="No activity yet" />}
        {activities.data && activities.data.total > 0 && (
          <>
            <div className="relative">
              <motion.span
                className="absolute top-3 left-[13px] w-px origin-top bg-line"
                initial={{ scaleY: 0 }}
                animate={{ scaleY: 1 }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
                style={{ bottom: 12 }}
              />
              <Stagger as="ol" key={offset} step={0.07}>
                {activities.data.items.map((activity) => (
                  <motion.li key={activity.id} variants={fadeUp} className="relative flex gap-3 pb-5 last:pb-0">
                    <motion.span
                      variants={{ hidden: { scale: 0 }, show: { scale: 1 } }}
                      transition={{ type: 'spring', stiffness: 400, damping: 15 }}
                      className={`relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border ${
                        activity.channel === 'ai' || activity.activity_type === 'ai' ? 'border-ai/30 bg-ai-surface text-ai' : 'border-line bg-surface text-ink-muted'
                      }`}
                    >
                      <Icon name={CHANNEL_ICON[activity.channel ?? activity.activity_type] ?? 'bolt'} className="text-base!" />
                    </motion.span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="font-semibold">{activity.description}</p>
                        <span className="font-mono text-[11px] text-ink-subtle" title={new Date(activity.created_at).toLocaleString()}>
                          {relativeTime(activity.created_at)}
                        </span>
                      </div>
                      <p className="text-xs text-ink-subtle">
                        {titleCase(activity.activity_type)}
                        {activity.channel && ` · ${activity.channel}`}
                      </p>
                      {Object.keys(activity.metadata).length > 0 && (
                        <details className="group mt-1.5">
                          <summary className="inline-flex cursor-pointer list-none items-center gap-0.5 text-xs text-ink-muted hover:text-primary">
                            <Icon name="chevron_right" className="text-base! transition-transform group-open:rotate-90" />
                            Details
                          </summary>
                          <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-sm bg-canvas p-2.5 text-xs">
                            {Object.entries(activity.metadata).map(([key, value]) => (
                              <div key={key} className="contents">
                                <dt className="text-ink-subtle">{key}</dt>
                                <dd className="font-mono break-all">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
                              </div>
                            ))}
                          </dl>
                        </details>
                      )}
                    </div>
                  </motion.li>
                ))}
              </Stagger>
            </div>
            <Pagination total={activities.data.total} offset={offset} onChange={setOffset} />
          </>
        )}
      </div>
    </Card>
  )
}

function Details({ lead }: { lead: LeadDetail }) {
  const days = daysSince(lead.last_contact_at)
  const rows: [string, React.ReactNode][] = [
    ['Email', lead.email],
    ['Phone', lead.phone && <span key="phone" className="font-mono">{lead.phone}</span>],
    ['Source', <SourceChip key="source" source={lead.source} />],
    ['External ID', lead.external_id && <span key="external" className="font-mono">{lead.external_id}</span>],
    ['Created', <span key="created" className="font-mono">{new Date(lead.created_at).toLocaleDateString()}</span>],
  ]
  return (
    <Card>
      <CardHeader title="Details" icon="badge" />
      <dl className="divide-y divide-line px-5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-4 py-2.5 text-[13px]">
            <dt className="text-ink-subtle">{label}</dt>
            <dd className="min-w-0 truncate text-right">{value || '—'}</dd>
          </div>
        ))}
      </dl>
      <div
        className={`mx-4 mb-4 flex items-center justify-between rounded-sm px-3 py-2 text-[13px] ${days == null || days > 7 ? 'bg-hot-surface text-hot' : 'bg-canvas text-ink-muted'}`}
      >
        <span>Last contact</span>
        <span className="flex items-center gap-1 font-mono text-xs">
          <Icon name="schedule" className="text-sm!" />
          {relativeTime(lead.last_contact_at)}
        </span>
      </div>
      {lead.follow_up && (
        <div
          className={`mx-4 mb-4 flex items-center justify-between rounded-sm px-3 py-2 text-[13px] ${lead.follow_up.overdue ? 'bg-hot-surface text-hot' : 'bg-canvas text-ink-muted'}`}
          title={new Date(lead.follow_up.due_at).toLocaleString()}
        >
          <span>{FOLLOW_UP_REASON[lead.follow_up.reason]}</span>
          <span className="flex items-center gap-1 font-mono text-xs">
            <Icon name="event_upcoming" className="text-sm!" />
            {dueLabel(lead.follow_up)}
          </span>
        </div>
      )}
    </Card>
  )
}

function LeadEditor({ businessId, lead }: { businessId: string; lead: LeadDetail }) {
  const update = useLeadMutation<LeadDetail>(businessId, `/leads/${lead.id}`, 'PATCH')
  const [toast, setToast] = useState(false)
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(false), 2600)
    return () => clearTimeout(timer)
  }, [toast])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const priority = data.get('priority') || null
    update.mutate(
      {
        status: data.get('status'),
        // Only a changed priority is sent: sending it marks it as picked by hand (kept until the score changes).
        ...(priority !== lead.priority && { priority }),
        notes: data.get('notes') || null,
      },
      { onSuccess: () => setToast(true) },
    )
  }
  return (
    <Card>
      <CardHeader title="Update lead" icon="edit_note" />
      <form className="space-y-3.5 p-5" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
            Status
            <input className={inputClass} name="status" defaultValue={lead.status} required maxLength={50} />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted" title="Set automatically from the score. A priority you pick stays until the score changes.">
            Priority
            <select className={inputClass} name="priority" defaultValue={lead.priority ?? ''}>
              <option value="">Unassigned</option>
              {['low', 'medium', 'high', 'critical'].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
          Notes
          <textarea dir="auto" className={`${inputClass} h-auto py-2`} name="notes" defaultValue={lead.notes ?? ''} rows={4} />
        </label>
        {update.isError && <ErrorState message={update.error.message} />}
        <Button type="submit" icon={update.isPending ? 'progress_activity' : 'save'} disabled={update.isPending} className="w-full">
          {update.isPending ? 'Saving…' : 'Save changes'}
        </Button>
      </form>
      <Toast show={toast}>Changes saved.</Toast>
    </Card>
  )
}

function CustomFields({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields)
  if (!entries.length) return null
  return (
    <Card>
      <CardHeader title="Custom fields" icon="tune" />
      <dl className="divide-y divide-line px-5">
        {entries.map(([key, value]) => (
          <div key={key} className="flex justify-between gap-4 py-2.5 text-[13px]">
            <dt className="text-ink-subtle">{titleCase(key)}</dt>
            <dd className="min-w-0 text-right font-mono text-xs break-words">
              {value !== null && typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}

// The lead's AI-drafted replies, newest first; shown only once there is one (WhatsApp leads).
function Replies({ businessId, leadId }: { businessId: string; leadId: string }) {
  const replies = useLeadReplies(businessId, leadId)
  if (!replies.data?.length) return null
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Replies" icon="forum" />
      <div className="divide-y divide-line">
        {replies.data.map((draft) => (
          <ReplyDraftCard key={draft.id} businessId={businessId} draft={draft} />
        ))}
      </div>
    </Card>
  )
}

function LeadSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true">
      <Skeleton className="h-36" />
      <div className="grid gap-5 lg:grid-cols-3">
        <Skeleton className="h-80 lg:col-span-2" />
        <Skeleton className="h-80" />
      </div>
    </div>
  )
}

export function LeadPage() {
  const { businessId = '', leadId = '' } = useParams()
  const query = useLead(businessId, leadId)
  const lead = query.data
  return (
    <div className="space-y-5">
      <Link className="inline-flex items-center gap-1 text-xs text-ink-subtle hover:text-primary" to={`/businesses/${businessId}/leads`}>
        <Icon name="arrow_back" className="text-sm!" /> Back to leads
      </Link>
      {query.isPending && <LeadSkeleton />}
      {query.isError && <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />}
      {lead && (
        <Stagger className="space-y-5" step={0.08}>
          <LeadHeader lead={lead} />
          <div className="grid items-start gap-5 lg:grid-cols-3">
            <Stagger className="space-y-5 lg:col-span-2" step={0.1}>
              <Replies businessId={businessId} leadId={leadId} />
              <Analysis businessId={businessId} lead={lead} key={lead.id} />
              <Timeline businessId={businessId} leadId={leadId} key={`${businessId}/${leadId}`} />
            </Stagger>
            <Stagger className="space-y-5" step={0.1} delay={0.15}>
              <Details lead={lead} />
              <ScoreCard businessId={businessId} lead={lead} />
              <LeadEditor businessId={businessId} lead={lead} key={lead.id} />
              <CustomFields fields={lead.custom_fields} />
            </Stagger>
          </div>
        </Stagger>
      )}
    </div>
  )
}
