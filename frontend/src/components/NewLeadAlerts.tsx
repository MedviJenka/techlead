import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router'

import { apiFetch } from '../api/client'
import { businessPath } from '../api/leads'
import type { Lead, Page } from '../api/types'
import { leadName, titleCase } from './leadDisplay'
import { spring } from './motion'
import { Avatar, Icon } from './ui'

const POLL_MS = 20_000
const WATCH_LIMIT = 20
const MAX_CARDS = 3

// Polls the newest leads and announces the ones that arrive while the app is open (WhatsApp, webhooks, a teammate).
// Leads that were already there on the first load, or that this tab is importing or creating itself, are not announced.
// Mount with key={businessId} so switching businesses starts from a fresh baseline.
export function NewLeadAlerts({ businessId }: { businessId: string }) {
  const client = useQueryClient()
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Lead[]>([])

  // Under ['businesses', id] so this tab's own lead mutations refetch it while they are still pending.
  const { data } = useQuery({
    queryKey: ['businesses', businessId, 'new-lead-watch'],
    queryFn: () => apiFetch<Page<Lead>>(`${businessPath(businessId)}/leads?limit=${WATCH_LIMIT}`),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    staleTime: 0,
  })

  useEffect(() => {
    if (!data) return
    if (seen.current === null) {
      seen.current = new Set(data.items.map((lead) => lead.id))
      return
    }
    const known = seen.current
    const arrived = data.items.filter((lead) => !known.has(lead.id))
    arrived.forEach((lead) => known.add(lead.id))
    if (!arrived.length || client.isMutating() > 0) return
    setFresh((current) => [...arrived, ...current])
    void client.invalidateQueries({
      queryKey: ['businesses', businessId],
      predicate: (query) => query.queryKey[2] !== 'new-lead-watch',
    })
  }, [businessId, client, data])

  useEffect(() => {
    if (!fresh.length) return
    const title = document.title
    document.title = `(${fresh.length}) ${title}`
    return () => {
      document.title = title
    }
  }, [fresh.length])

  const dismiss = (id: string) => setFresh((current) => current.filter((lead) => lead.id !== id))
  const overflow = fresh.length - MAX_CARDS

  // Portaled: a fixed element inside a transformed (animated) ancestor would be positioned against that ancestor.
  return createPortal(
    <div
      aria-live="polite"
      className="fixed top-16 right-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2"
    >
      <AnimatePresence initial={false}>
        {fresh.slice(0, MAX_CARDS).map((lead) => (
          <motion.div
            key={lead.id}
            layout
            role="status"
            initial={{ opacity: 0, x: 24, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24, scale: 0.97 }}
            transition={spring}
            className="flex items-center gap-3 rounded-md border border-line bg-surface p-3 shadow-lift"
          >
            <Avatar name={leadName(lead)} size="sm" />
            <Link
              to={`/businesses/${businessId}/leads/${lead.id}`}
              onClick={() => dismiss(lead.id)}
              className="min-w-0 flex-1"
            >
              <p className="text-xs font-medium text-primary">New lead</p>
              <p className="truncate text-sm font-semibold">{leadName(lead)}</p>
              <p className="truncate text-xs text-ink-muted">
                via {titleCase(lead.source)}
                {lead.company_name ? ` · ${lead.company_name}` : ''}
              </p>
            </Link>
            <button
              type="button"
              onClick={() => dismiss(lead.id)}
              aria-label={`Dismiss new lead ${leadName(lead)}`}
              className="rounded-sm p-1 text-ink-subtle transition hover:bg-ink/5 hover:text-ink"
            >
              <Icon name="close" className="text-lg!" />
            </button>
          </motion.div>
        ))}
        {overflow > 0 && (
          <motion.div
            key="overflow"
            layout
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center justify-between rounded-md bg-ink px-3 py-2 text-sm text-white shadow-lift"
          >
            <Link to={`/businesses/${businessId}/leads`} onClick={() => setFresh([])}>
              +{overflow} more new {overflow === 1 ? 'lead' : 'leads'}
            </Link>
            <button type="button" onClick={() => setFresh([])} className="text-xs text-white/70 hover:text-white">
              Dismiss all
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>,
    document.body,
  )
}
