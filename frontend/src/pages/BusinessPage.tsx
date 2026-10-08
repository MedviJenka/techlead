import { motion } from 'motion/react'
import { Link, useParams } from 'react-router'

import { useBusiness } from '../api/hooks'
import { useDashboard } from '../api/leads'
import type { Bucket, Dashboard, Lead } from '../api/types'
import { LeadTable } from '../components/Leads'
import { daysSince, leadName, relativeTime, titleCase } from '../components/leadDisplay'
import { AnimatedNumber, Avatar, Card, CardHeader, EmptyState, ErrorState, Icon, PriorityFlag, Reveal, ScoreMeter, Skeleton, Stagger } from '../components/ui'
import { fadeUp, spring } from '../components/motion'

type Counts = Dashboard['counts']

const KPIS: { key: keyof Counts; label: string; icon: string; hint: string; filter?: string }[] = [
  { key: 'total', label: 'Total leads', icon: 'groups', hint: 'Every lead in this business.' },
  { key: 'new', label: 'New', icon: 'fiber_new', hint: 'Leads with status "new".', filter: 'status=new' },
  { key: 'hot', label: 'Hot', icon: 'local_fire_department', hint: 'High or critical priority.' },
  { key: 'qualified', label: 'Qualified', icon: 'verified', hint: 'Leads with status "qualified".', filter: 'status=qualified' },
  { key: 'needs_follow_up', label: 'Needs follow-up', icon: 'schedule', hint: 'Open leads never contacted, or last contacted over 7 days ago.' },
  { key: 'waiting_for_proposal', label: 'Waiting for proposal', icon: 'request_quote', hint: 'Qualified leads waiting for a proposal.' },
  { key: 'inactive', label: 'Inactive', icon: 'bedtime', hint: 'Marked inactive, or open with no contact for over 7 days since creation.' },
  { key: 'average_score', label: 'Avg score', icon: 'speed', hint: 'Mean lead score, 0–100.' },
]

function KpiTile({ businessId, kpi, value }: { businessId: string; kpi: (typeof KPIS)[number]; value: number | null }) {
  const hot = kpi.key === 'hot'
  return (
    <motion.div variants={fadeUp} whileHover={{ y: -3 }} transition={spring}>
      <Link
        to={`/businesses/${businessId}/leads${kpi.filter ? `?${kpi.filter}` : ''}`}
        title={kpi.hint}
        className={`group relative flex h-full flex-col overflow-hidden rounded-md border bg-surface p-4 transition-shadow hover:shadow-lift ${hot ? 'border-hot/30' : 'border-line'}`}
      >
        {hot && <span className="absolute inset-y-0 left-0 w-1 bg-hot" />}
        <span className="flex items-center justify-between text-[13px] text-ink-muted">
          {kpi.label}
          <Icon
            name={kpi.icon}
            fill={hot}
            className={`transition-transform group-hover:scale-125 ${hot ? 'animate-pulse text-hot' : 'text-ink-subtle group-hover:text-primary'}`}
          />
        </span>
        <span className={`mt-2 text-[28px] leading-none font-medium ${hot ? 'text-hot' : ''}`}>
          {value == null ? <span className="font-mono text-ink-subtle">—</span> : <AnimatedNumber value={value} decimals={Number.isInteger(value) ? 0 : 1} />}
        </span>
        <span className="mt-2 truncate text-xs text-ink-subtle">{kpi.hint}</span>
      </Link>
    </motion.div>
  )
}

function TodayStrip({ businessId, leads }: { businessId: string; leads: Lead[] }) {
  const picks = leads.slice(0, 3)
  if (!picks.length) return null
  return (
    <Reveal>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-[15px] font-bold">Today</h2>
        <span className="font-mono text-[11px] text-ink-subtle">who to contact right now</span>
      </div>
      <Stagger className="grid gap-3 lg:grid-cols-3" step={0.08}>
        {picks.map((lead, index) => {
          const days = daysSince(lead.last_contact_at)
          return (
            <Card key={lead.id} interactive className="relative overflow-hidden p-4">
              {index === 0 && <span className="absolute top-0 right-0 rounded-bl-md bg-hot px-2 py-0.5 font-mono text-[10px] text-white">#1</span>}
              <Link to={`/businesses/${businessId}/leads/${lead.id}`} className="flex items-center gap-3">
                <Avatar name={leadName(lead)} hot={(lead.lead_score ?? 0) >= 80} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{leadName(lead)}</p>
                  <p className="truncate text-xs text-ink-subtle">{lead.company_name ?? lead.source}</p>
                </div>
                <PriorityFlag priority={lead.priority} />
              </Link>
              <div className="mt-3 flex items-center justify-between gap-3">
                <ScoreMeter score={lead.lead_score} />
                <span className={`font-mono text-[11px] ${days == null || days > 7 ? 'text-hot' : 'text-ink-subtle'}`}>
                  {days == null ? 'never contacted' : `no contact · ${days}d`}
                </span>
              </div>
              {lead.recommended_action && <p className="mt-3 line-clamp-2 text-xs text-ink-muted">{lead.recommended_action}</p>}
              <div className="mt-3 flex gap-2">
                {lead.phone && (
                  <a href={`tel:${lead.phone}`} className="inline-flex h-7 items-center gap-1 rounded-sm bg-primary px-2.5 text-xs font-medium text-white transition hover:bg-primary-hover">
                    <Icon name="call" className="text-base!" /> Call
                  </a>
                )}
                {lead.phone && (
                  <a
                    href={`https://wa.me/${lead.phone.replace(/\D/g, '')}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-7 items-center gap-1 rounded-sm border border-line px-2.5 text-xs font-medium transition hover:bg-canvas"
                  >
                    <Icon name="chat" className="text-base!" /> WhatsApp
                  </a>
                )}
                {lead.email && (
                  <a href={`mailto:${lead.email}`} className="inline-flex h-7 items-center gap-1 rounded-sm border border-line px-2.5 text-xs font-medium transition hover:bg-canvas">
                    <Icon name="mail" className="text-base!" /> Email
                  </a>
                )}
              </div>
            </Card>
          )
        })}
      </Stagger>
    </Reveal>
  )
}

const BAR_TONES = ['bg-primary', 'bg-ai', 'bg-hot', 'bg-warning', 'bg-sky-500', 'bg-success', 'bg-ink-subtle']

function SourceBars({ buckets }: { buckets: Bucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.count))
  return (
    <div className="space-y-3">
      {buckets.map((bucket, index) => (
        <div key={bucket.key} className="text-[13px]">
          <div className="flex justify-between gap-3">
            <span>{titleCase(bucket.key)}</span>
            <AnimatedNumber value={bucket.count} className="text-ink-muted" />
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-canvas">
            <motion.div
              className="h-full rounded-full bg-primary"
              initial={{ width: 0 }}
              whileInView={{ width: `${(bucket.count / max) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.9, delay: index * 0.07, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function StatusStack({ buckets }: { buckets: Bucket[] }) {
  const total = Math.max(1, buckets.reduce((sum, b) => sum + b.count, 0))
  return (
    <div>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full">
        {buckets.map((bucket, index) => (
          <motion.div
            key={bucket.key}
            title={`${titleCase(bucket.key)}: ${bucket.count}`}
            className={BAR_TONES[index % BAR_TONES.length]}
            initial={{ width: 0 }}
            whileInView={{ width: `${(bucket.count / total) * 100}%` }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: index * 0.08, ease: [0.16, 1, 0.3, 1] }}
          />
        ))}
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
        {buckets.map((bucket, index) => (
          <li key={bucket.key} className="flex items-center gap-2">
            <span className={`size-2 rounded-full ${BAR_TONES[index % BAR_TONES.length]}`} />
            <span className="flex-1 truncate">{titleCase(bucket.key)}</span>
            <span className="font-mono text-ink-muted">{bucket.count}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ScoreHistogram({ buckets }: { buckets: Bucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.count))
  const tone = (key: string) => (key.startsWith('80') ? 'bg-hot' : key.startsWith('50') ? 'bg-primary' : 'bg-ink-subtle/60')
  return (
    <div className="flex h-36 items-end gap-3">
      {buckets.map((bucket, index) => (
        <div key={bucket.key} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
          <span className="font-mono text-xs text-ink-muted">{bucket.count}</span>
          <motion.div
            className={`w-full rounded-t-sm ${tone(bucket.key)}`}
            initial={{ height: 0 }}
            whileInView={{ height: `${Math.max(4, (bucket.count / max) * 100)}%` }}
            viewport={{ once: true }}
            transition={{ type: 'spring', stiffness: 120, damping: 16, delay: index * 0.1 }}
          />
          <span className="font-mono text-[11px] text-ink-subtle">{bucket.key}</span>
        </div>
      ))}
    </div>
  )
}

function Distribution({ title, icon, buckets, children }: { title: string; icon: string; buckets: Bucket[]; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} icon={icon} />
      <div className="p-5">{buckets.length ? children : <p className="text-ink-subtle">No data yet.</p>}</div>
    </Card>
  )
}

const ACTIVITY_ICON: Record<string, string> = {
  call: 'call',
  whatsapp: 'chat',
  email: 'mail',
  note: 'sticky_note_2',
  status_change: 'swap_horiz',
  import: 'upload',
  system: 'settings',
}

function RecentActivity({ businessId, items }: { businessId: string; items: Dashboard['recent_activity'] }) {
  if (!items.length)
    return (
      <EmptyState icon="history" title="No activity yet">
        <Link to={`/businesses/${businessId}/leads?import=1`} className="text-sm font-medium text-primary hover:underline">
          Import leads to get started
        </Link>
      </EmptyState>
    )
  return (
    <Stagger as="ol" className="relative px-5 py-4" step={0.05}>
      <span className="absolute top-6 bottom-6 left-[34px] w-px bg-line" />
      {items.map((activity) => (
        <motion.li key={activity.id} variants={fadeUp} className="relative flex gap-3 py-2.5">
          <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-ink-muted">
            <Icon name={ACTIVITY_ICON[activity.channel ?? activity.activity_type] ?? 'bolt'} className="text-base!" />
          </span>
          <div className="min-w-0 flex-1 text-[13px]">
            <Link to={`/businesses/${businessId}/leads/${activity.lead_id}`} className="font-semibold hover:text-primary">
              {activity.lead_name || 'Unnamed lead'}
            </Link>
            <p className="text-ink-muted">{activity.description}</p>
          </div>
          <span className="shrink-0 font-mono text-[11px] text-ink-subtle" title={new Date(activity.created_at).toLocaleString()}>
            {relativeTime(activity.created_at)}
          </span>
        </motion.li>
      ))}
    </Stagger>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="grid gap-3 lg:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-40" />)}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {KPIS.map((k) => <Skeleton key={k.key} className="h-28" />)}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}
      </div>
    </div>
  )
}

export function BusinessPage() {
  const { businessId = '' } = useParams()
  const business = useBusiness(businessId)
  const dashboard = useDashboard(businessId)
  const data = dashboard.data

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          {business.data ? (
            <motion.h1 initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="text-2xl font-bold tracking-tight">
              {business.data.name}
            </motion.h1>
          ) : (
            <Skeleton className="h-8 w-56" />
          )}
          <p className="mt-1 flex items-center gap-2 text-ink-muted">
            {business.data && [business.data.industry, business.data.timezone].filter(Boolean).join(' · ')}
            {data && (
              <span className="font-mono text-[11px] text-ink-subtle">· updated {relativeTime(data.generated_at)}</span>
            )}
          </p>
        </div>
        <Link
          className="group inline-flex h-9 items-center gap-1.5 rounded-sm bg-primary px-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-primary-hover"
          to={`/businesses/${businessId}/leads`}
        >
          View all leads
          <Icon name="arrow_forward" className="text-lg! transition-transform group-hover:translate-x-1" />
        </Link>
      </div>

      {(business.isError || dashboard.isError) && (
        <ErrorState
          message={business.error?.message || dashboard.error?.message || 'Could not load the dashboard.'}
          onRetry={() => {
            void business.refetch()
            void dashboard.refetch()
          }}
        />
      )}
      {dashboard.isPending && <DashboardSkeleton />}

      {data && (
        <Stagger className="space-y-6" step={0.08}>
          <TodayStrip businessId={businessId} leads={data.top_leads} />

          <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-4" step={0.04}>
            {KPIS.map((kpi) => (
              <KpiTile key={kpi.key} businessId={businessId} kpi={kpi} value={data.counts[kpi.key]} />
            ))}
          </Stagger>

          <div className="grid gap-4 md:grid-cols-3">
            <Distribution title="By source" icon="hub" buckets={data.by_source}>
              <SourceBars buckets={data.by_source} />
            </Distribution>
            <Distribution title="By status" icon="donut_small" buckets={data.by_status}>
              <StatusStack buckets={data.by_status} />
            </Distribution>
            <Distribution title="By score" icon="bar_chart" buckets={data.by_score}>
              <ScoreHistogram buckets={data.by_score} />
            </Distribution>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
            <Card className="overflow-hidden">
              <CardHeader
                title="Top open leads"
                icon="trending_up"
                action={
                  <Link to={`/businesses/${businessId}/leads`} className="text-xs font-medium text-primary hover:underline">
                    View all
                  </Link>
                }
              />
              <LeadTable businessId={businessId} leads={data.top_leads.slice(0, 8)} compact bare />
            </Card>
            <Card>
              <CardHeader title="Recent activity" icon="history" />
              <RecentActivity businessId={businessId} items={data.recent_activity} />
            </Card>
          </div>
        </Stagger>
      )}

      {business.data && (
        <details className="group rounded-md border border-line bg-surface">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-3.5 font-medium text-ink-muted">
            <Icon name="chevron_right" className="transition-transform group-open:rotate-90" />
            Business configuration
          </summary>
          <div className="border-t border-line px-5 py-4">
            <p className="text-[13px]">
              Slug: <span className="font-mono">{business.data.slug}</span>
            </p>
            <pre className="mt-3 overflow-x-auto rounded-sm bg-canvas p-3 font-mono text-xs">
              {JSON.stringify(business.data.ai_configuration, null, 2)}
            </pre>
          </div>
        </details>
      )}
    </div>
  )
}
