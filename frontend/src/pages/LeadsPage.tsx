import { AnimatePresence, motion } from 'motion/react'
import { useState, type DragEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { useImport, useLeads } from '../api/leads'
import type { ImportResult } from '../api/types'
import { LeadTable, Pagination } from '../components/Leads'
import { inputClass } from '../components/leadDisplay'
import { AnimatedNumber, Button, ErrorState, Icon, Skeleton } from '../components/ui'
import { spring } from '../components/motion'

// The list endpoint forbids unknown query parameters (LeadListParams), so only these reach it. Anything else in
// the URL (`import`, or the `code` the Google sign-in redirect leaves behind) stays in the page.
const API_PARAMS = ['status', 'priority', 'source', 'q', 'limit', 'offset']

const QUICK_FILTERS: { label: string; params: Record<string, string>; hot?: boolean }[] = [
  { label: 'All', params: {} },
  { label: 'Critical', params: { priority: 'critical' }, hot: true },
  { label: 'High priority', params: { priority: 'high' }, hot: true },
  { label: 'New', params: { status: 'new' } },
  { label: 'Qualified', params: { status: 'qualified' } },
  { label: 'Inactive', params: { status: 'inactive' } },
]
const FILTER_KEYS = ['status', 'priority', 'source', 'q']

function ImportCounters({ result }: { result: ImportResult }) {
  const counters = [
    { label: 'Created', value: result.created, tone: 'text-success', icon: 'add_circle' },
    { label: 'Updated', value: result.updated, tone: 'text-primary', icon: 'sync' },
    { label: 'Skipped', value: result.skipped, tone: 'text-ink-muted', icon: 'skip_next' },
    { label: 'Failed', value: result.failed, tone: 'text-danger', icon: 'error' },
  ]
  const failures = result.results.filter((row) => row.errors)
  return (
    <div role="status" className="mt-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {counters.map((counter, index) => (
          <motion.div
            key={counter.label}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ ...spring, delay: index * 0.07 }}
            className="rounded-md border border-line bg-canvas/50 p-3"
          >
            <span className={`flex items-center gap-1.5 text-xs ${counter.tone}`}>
              <Icon name={counter.icon} fill className="text-base!" />
              {counter.label}
            </span>
            <AnimatedNumber value={counter.value} className="mt-1 block text-2xl" />
          </motion.div>
        ))}
      </div>
      {failures.length > 0 && (
        <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto rounded-sm border border-danger/20 bg-danger/5 p-3 text-xs text-danger">
          {failures.map((row) => (
            <li key={row.index}>
              <span className="font-mono">
                #{row.index + 1} {row.external_id ?? 'no ID'}
              </span>{' '}
              {row.errors?.map((error) => `${error.loc.join('.')}: ${error.msg}`).join('; ')}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ImportPanel({ businessId, onClose }: { businessId: string; onClose: () => void }) {
  const importer = useImport(businessId)
  const [fileError, setFileError] = useState('')
  const [reading, setReading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const busy = reading || importer.isPending

  const importFile = async (file: File) => {
    setFileError('')
    importer.reset()
    setReading(true)
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Choose a JSON file smaller than 10 MB.')
      const payload: unknown = JSON.parse(await file.text())
      importer.mutate(Array.isArray(payload) ? { leads: payload } : payload)
    } catch (error) {
      setFileError(error instanceof Error ? error.message : 'Could not read file')
    } finally {
      setReading(false)
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file && !busy) void importFile(file)
  }

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="overflow-hidden"
    >
      <section className="rounded-md border border-line bg-surface p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <Icon name="upload_file" className="text-primary" />
            Import leads from JSON
          </h2>
          <button type="button" onClick={onClose} aria-label="Close import" className="rounded-sm p-1 text-ink-subtle hover:bg-ink/5 hover:text-ink">
            <Icon name="close" />
          </button>
        </div>
        <motion.label
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          animate={{ scale: dragging ? 1.015 : 1 }}
          transition={spring}
          className={`relative flex cursor-pointer flex-col items-center gap-2 overflow-hidden rounded-md border-2 border-dashed px-6 py-8 text-center transition-colors ${
            dragging ? 'border-primary bg-primary-soft' : 'border-line hover:border-primary/50 hover:bg-canvas/60'
          } ${busy ? 'pointer-events-none' : ''}`}
        >
          {busy && <span className="skeleton absolute inset-x-0 bottom-0 h-1" />}
          <motion.span
            animate={busy ? { y: [0, -6, 0] } : dragging ? { y: -4, scale: 1.15 } : { y: 0, scale: 1 }}
            transition={busy ? { duration: 0.9, repeat: Infinity } : spring}
            className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary"
          >
            <Icon name={busy ? 'hourglass_top' : 'cloud_upload'} className="text-2xl!" />
          </motion.span>
          <span className="font-medium">{busy ? 'Importing…' : dragging ? 'Drop to import' : 'Drop a .json file here, or click to browse'}</span>
          <span className="text-xs text-ink-subtle">Sample dataset format with a leads array · up to 10 MB, 1,000 records</span>
          <input
            className="sr-only"
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void importFile(file)
              event.target.value = ''
            }}
          />
        </motion.label>
        {(fileError || importer.isError) && (
          <div className="mt-4">
            <ErrorState message={fileError || importer.error?.message || 'Import failed'} />
          </div>
        )}
        {importer.data && <ImportCounters result={importer.data} />}
      </section>
    </motion.div>
  )
}

function TableSkeleton() {
  return (
    <div className="space-y-px overflow-hidden rounded-md border border-line bg-surface" aria-busy="true">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3">
          <Skeleton className="size-7 rounded-full" />
          <Skeleton className="h-3.5 w-40" />
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="ml-auto h-3.5 w-24" />
        </div>
      ))}
    </div>
  )
}

export function LeadsPage() {
  const { businessId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const apiParams = new URLSearchParams([...params].filter(([key]) => API_PARAMS.includes(key)))
  const leads = useLeads(businessId, apiParams.toString())
  const offset = Number(params.get('offset') || 0)
  const importOpen = params.has('import')

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('offset' in changes)) next.delete('offset')
    setParams(next)
  }

  const activeQuick = QUICK_FILTERS.find(
    (filter) =>
      ['status', 'priority'].every((key) => (params.get(key) ?? '') === (filter.params[key] ?? '')) &&
      !params.get('source'),
  )

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link className="inline-flex items-center gap-1 text-xs text-ink-subtle hover:text-primary" to={`/businesses/${businessId}`}>
            <Icon name="arrow_back" className="text-sm!" /> Dashboard
          </Link>
          <h1 className="mt-1 flex items-baseline gap-3 text-2xl font-bold tracking-tight">
            Leads
            {leads.data && (
              <span className="font-mono text-sm font-medium text-ink-subtle">
                <AnimatedNumber value={leads.data.total} /> leads
              </span>
            )}
          </h1>
        </div>
        <Button icon={importOpen ? 'close' : 'upload'} variant={importOpen ? 'ghost' : 'primary'} onClick={() => update({ import: importOpen ? null : '1', offset: String(offset || '') })}>
          {importOpen ? 'Close import' : 'Import'}
        </Button>
      </div>

      <AnimatePresence initial={false}>{importOpen && <ImportPanel businessId={businessId} onClose={() => update({ import: null, offset: String(offset || '') })} />}</AnimatePresence>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Quick filters">
          {QUICK_FILTERS.map((filter) => {
            const active = activeQuick?.label === filter.label
            return (
              <button
                key={filter.label}
                type="button"
                aria-pressed={active}
                onClick={() => update({ status: filter.params.status ?? null, priority: filter.params.priority ?? null, source: null })}
                className={`relative h-8 rounded-full px-3.5 text-[13px] font-medium transition-colors ${active ? (filter.hot ? 'text-hot' : 'text-primary') : 'text-ink-muted hover:text-ink'}`}
              >
                {active && (
                  <motion.span
                    layoutId="quick-filter"
                    transition={spring}
                    className={`absolute inset-0 rounded-full border ${filter.hot ? 'border-hot/30 bg-hot-surface' : 'border-primary/25 bg-primary-soft'}`}
                  />
                )}
                <span className="relative flex items-center gap-1">
                  {filter.hot && <Icon name="local_fire_department" fill={active} className="text-base!" />}
                  {filter.label}
                </span>
              </button>
            )
          })}
        </div>

        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            update({ q: String(data.get('q') || '').trim() })
          }}
        >
          <div className="relative min-w-64 flex-1">
            <Icon name="search" className="absolute top-1/2 left-3 -translate-y-1/2 text-ink-subtle" />
            <input
              key={params.get('q') ?? ''}
              aria-label="Search leads"
              name="q"
              defaultValue={params.get('q') ?? ''}
              placeholder="Search name, email, phone, company"
              className={`${inputClass} w-full pl-10`}
              maxLength={100}
            />
          </div>
          <input
            aria-label="Filter by status"
            placeholder="Status"
            className={`${inputClass} w-32`}
            value={params.get('status') ?? ''}
            onChange={(event) => update({ status: event.target.value })}
          />
          <input
            aria-label="Filter by source"
            placeholder="Source"
            className={`${inputClass} w-32`}
            value={params.get('source') ?? ''}
            onChange={(event) => update({ source: event.target.value })}
          />
          <select
            aria-label="Filter by priority"
            className={inputClass}
            value={params.get('priority') ?? ''}
            onChange={(event) => update({ priority: event.target.value })}
          >
            <option value="">All priorities</option>
            {['low', 'medium', 'high', 'critical'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <Button variant="ghost" icon="search" type="submit">
            Search
          </Button>
          <AnimatePresence>
            {FILTER_KEYS.some((key) => params.get(key)) && (
              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}>
                <Button variant="subtle" icon="filter_alt_off" type="button" onClick={() => update(Object.fromEntries(FILTER_KEYS.map((key) => [key, null])))}>
                  Clear
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </form>
      </div>

      {leads.isError && <ErrorState message={leads.error.message} onRetry={() => void leads.refetch()} />}
      {leads.isPending && <TableSkeleton />}
      {leads.data && (
        <div>
          <LeadTable key={apiParams.toString()} businessId={businessId} leads={leads.data.items} />
          <Pagination total={leads.data.total} offset={offset} onChange={(value) => update({ offset: String(value) })} />
        </div>
      )}
    </div>
  )
}
