import { motion } from 'motion/react'
import { Link, useNavigate } from 'react-router'

import type { Lead } from '../api/types'
import { daysSince, dueLabel, leadName, relativeTime } from './leadDisplay'
import { Avatar, Button, EmptyState, Icon, PriorityFlag, ScoreMeter, SourceChip, StatusChip } from './ui'

const PAGE_SIZE = 25
const MAX_OFFSET = 10_000

const rowVariants = {
  hidden: { opacity: 0, y: 8 },
  show: (index: number) => ({ opacity: 1, y: 0, transition: { delay: index * 0.035, duration: 0.35, ease: [0.22, 1, 0.36, 1] as const } }),
}

export function LeadTable({
  businessId,
  leads,
  compact,
  bare,
}: {
  businessId: string
  leads: Lead[]
  /** Drops the source and last-contact columns (dashboard card). */
  compact?: boolean
  /** No outer border: the table sits inside a Card. */
  bare?: boolean
}) {
  const navigate = useNavigate()
  if (!leads.length)
    return (
      <EmptyState icon="person_search" title="No leads found">
        <p className="text-ink-muted">Try another filter, or import a JSON file.</p>
      </EmptyState>
    )
  const columns = compact
    ? ['Lead', 'Status', 'Priority', 'Score']
    : ['Lead', 'Source', 'Status', 'Priority', 'Score', 'Last contact', 'Follow-up']
  return (
    <div className={`overflow-x-auto ${bare ? '' : 'rounded-md border border-line bg-surface'}`}>
      <table className="w-full text-left text-[13px]">
        <thead className="sticky top-0 bg-canvas/60 text-xs text-ink-muted">
          <tr>
            {columns.map((label) => (
              <th className="px-4 py-2.5 font-medium" key={label}>
                {label}
              </th>
            ))}
            <th className="w-10" aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {leads.map((lead, index) => {
            const name = leadName(lead)
            const href = `/businesses/${businessId}/leads/${lead.id}`
            const days = daysSince(lead.last_contact_at)
            return (
              <motion.tr
                key={lead.id}
                custom={index}
                variants={rowVariants}
                initial="hidden"
                animate="show"
                onClick={(event) => {
                  if (!(event.target as HTMLElement).closest('a')) navigate(href)
                }}
                className="group relative cursor-pointer border-t border-line transition-colors hover:bg-primary-soft/40"
              >
                <td className="relative px-4 py-2.5">
                  <span className="absolute inset-y-1 left-0 w-0.5 origin-center scale-y-0 rounded-full bg-primary transition-transform group-hover:scale-y-100" />
                  <div className="flex items-center gap-3">
                    <Avatar name={name} size="sm" hot={(lead.lead_score ?? 0) >= 80} />
                    <div className="min-w-0">
                      <Link to={href} className="block truncate font-semibold transition-colors group-hover:text-primary">
                        {name}
                      </Link>
                      <span className="block truncate text-xs text-ink-subtle">{lead.company_name ?? lead.email ?? '—'}</span>
                    </div>
                  </div>
                </td>
                {!compact && (
                  <td className="px-4 py-2.5">
                    <SourceChip source={lead.source} />
                  </td>
                )}
                <td className="px-4 py-2.5">
                  <StatusChip status={lead.status} />
                </td>
                <td className="px-4 py-2.5">
                  <PriorityFlag priority={lead.priority} />
                </td>
                <td className="px-4 py-2.5">
                  <ScoreMeter score={lead.lead_score} />
                </td>
                {!compact && (
                  <td className={`px-4 py-2.5 font-mono text-xs ${days == null || days > 7 ? 'text-hot' : 'text-ink-muted'}`}>
                    {relativeTime(lead.last_contact_at)}
                  </td>
                )}
                {!compact && (
                  <td className={`px-4 py-2.5 font-mono text-xs ${lead.follow_up?.overdue ? 'font-medium text-hot' : 'text-ink-muted'}`}>
                    {lead.follow_up ? dueLabel(lead.follow_up) : '—'}
                  </td>
                )}
                <td className="pr-3">
                  <Icon name="chevron_right" className="text-ink-subtle opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
                </td>
              </motion.tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({
  total,
  offset,
  onChange,
}: {
  total: number
  offset: number
  onChange: (value: number) => void
}) {
  if (total <= PAGE_SIZE && offset === 0) return null
  const end = Math.min(offset + PAGE_SIZE, total)
  return (
    <div className="flex items-center justify-between gap-4 py-3 text-[13px]">
      <motion.span key={offset} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="font-mono text-ink-muted">
        {total ? offset + 1 : 0}–{end} of {total.toLocaleString()}
      </motion.span>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" icon="chevron_left" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={offset + PAGE_SIZE >= total || offset + PAGE_SIZE > MAX_OFFSET}
          onClick={() => onChange(offset + PAGE_SIZE)}
        >
          Next
          <Icon name="chevron_right" className="text-base!" />
        </Button>
      </div>
    </div>
  )
}
