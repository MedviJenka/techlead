import type { Lead } from '../api/types'

export const inputClass =
  'h-9 rounded-sm border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-subtle transition focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/15'

export const leadName = (lead: Pick<Lead, 'first_name' | 'last_name' | 'email'>) =>
  [lead.first_name, lead.last_name].filter(Boolean).join(' ') ||
  lead.email ||
  'Unnamed lead'

export const initials = (name: string) =>
  name
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join('') || '?'

export const titleCase = (value: string) =>
  value.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase())

const DAY = 86_400_000

export const daysSince = (iso: string | null) =>
  iso ? Math.floor((Date.now() - new Date(iso).getTime()) / DAY) : null

export function relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export const isHot = (priority: string | null) => priority === 'high' || priority === 'critical'
