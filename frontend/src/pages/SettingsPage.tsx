import { useEffect, useState, type ReactNode } from 'react'
import { useParams } from 'react-router'

import { useBusiness, useUpdateSettings } from '../api/hooks'
import { useRescore } from '../api/leads'
import type {
  Business,
  BusinessConfiguration,
  Condition,
  ConditionOp,
  CustomFieldDefinition,
  CustomFieldType,
  PriorityName,
  Scalar,
  ScoringRule,
} from '../api/types'
import { inputClass, titleCase } from '../components/leadDisplay'
import { WhatsAppSettings } from '../components/WhatsAppSettings'
import { Button, Card, CardHeader, ErrorState, Icon, Skeleton, Stagger, Toast } from '../components/ui'

// Mirrors FACT_NAMES in app/schemas/configuration.py.
const FACTS = [
  'status',
  'source',
  'sentiment',
  'has_email',
  'has_phone',
  'has_company',
  'notes',
  'budget',
  'budget_known',
  'timeframe_days',
  'replied',
  'contact_attempts',
  'ignored_follow_ups',
  'days_since_created',
  'days_since_last_contact',
  'proposal_sent',
  'meeting_scheduled',
]
const OPS: { op: ConditionOp; label: string }[] = [
  { op: 'eq', label: 'is' },
  { op: 'ne', label: 'is not' },
  { op: 'gt', label: '>' },
  { op: 'gte', label: '≥' },
  { op: 'lt', label: '<' },
  { op: 'lte', label: '≤' },
  { op: 'in', label: 'is one of' },
  { op: 'contains', label: 'contains' },
  { op: 'exists', label: 'is set' },
  { op: 'missing', label: 'is not set' },
]
const PRIORITIES: PriorityName[] = ['critical', 'high', 'medium', 'low']
const FIELD_TYPES: CustomFieldType[] = ['text', 'number', 'boolean', 'date', 'select']

const opLabel = (op: ConditionOp) => OPS.find((item) => item.op === op)?.label ?? op
const takesValue = (op: ConditionOp) => op !== 'exists' && op !== 'missing'

function parseScalar(text: string): Scalar {
  const value = text.trim()
  if (value === 'true' || value === 'false') return value === 'true'
  if (value !== '' && !Number.isNaN(Number(value))) return Number(value)
  return value
}

function parseValue(op: ConditionOp, text: string): Condition['value'] {
  if (!takesValue(op)) return null
  if (op === 'in') return text.split(',').filter((part) => part.trim()).map(parseScalar)
  return parseScalar(text)
}

const describe = (condition: Condition) =>
  [condition.fact, opLabel(condition.op), Array.isArray(condition.value) ? condition.value.join(', ') : condition.value]
    .filter((part) => part !== null && part !== undefined)
    .join(' ')

const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/^(\d)/, 'r_$1')
    .slice(0, 50) || 'rule'

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted" title={hint}>
      {label}
      {children}
    </label>
  )
}

function NumberInput({ value, onChange, step = 1, min, max }: { value: number; onChange: (value: number) => void; step?: number; min?: number; max?: number }) {
  return (
    <input
      type="number"
      className={`${inputClass} w-full font-mono`}
      value={value}
      step={step}
      min={min}
      max={max}
      onChange={(event) => onChange(event.target.valueAsNumber)}
    />
  )
}

function RuleEditor({ rules, customKeys, onChange }: { rules: ScoringRule[]; customKeys: string[]; onChange: (rules: ScoringRule[]) => void }) {
  const [label, setLabel] = useState('')
  const [fact, setFact] = useState(FACTS[0]!)
  const [op, setOp] = useState<ConditionOp>('eq')
  const [value, setValue] = useState('')
  const [points, setPoints] = useState(10)

  const add = () => {
    const taken = new Set(rules.map((rule) => rule.id))
    let id = slug(label)
    for (let n = 2; taken.has(id); n++) id = `${slug(label)}_${n}`
    onChange([...rules, { id, label: label.trim(), points, when: [{ fact, op, value: parseValue(op, value) }] }])
    setLabel('')
    setValue('')
  }
  const facts = [...FACTS, ...customKeys.map((key) => `custom_fields.${key}`)]
  return (
    <div className="space-y-3">
      <ul className="divide-y divide-line rounded-sm border border-line">
        {rules.length === 0 && <li className="px-3 py-2.5 text-ink-subtle">No rules: every lead gets the starting score.</li>}
        {rules.map((rule, index) => (
          <li key={rule.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{rule.label}</p>
              <p className="font-mono text-[11px] text-ink-subtle">{rule.when.map(describe).join(' and ')}</p>
            </div>
            <div className="w-20">
              <NumberInput
                value={rule.points}
                min={-100}
                max={100}
                onChange={(next) => onChange(rules.map((item, i) => (i === index ? { ...item, points: next } : item)))}
              />
            </div>
            <Button type="button" variant="danger" size="sm" icon="delete" aria-label={`Remove ${rule.label}`} onClick={() => onChange(rules.filter((_, i) => i !== index))} />
          </li>
        ))}
      </ul>
      <div className="grid gap-2 rounded-sm bg-canvas p-3 sm:grid-cols-[2fr_1.5fr_1fr_1.2fr_0.8fr_auto] sm:items-end">
        <Field label="New rule">
          <input className={inputClass} placeholder="e.g. Mortgage approved" value={label} maxLength={100} onChange={(event) => setLabel(event.target.value)} />
        </Field>
        <Field label="When">
          <select className={inputClass} value={fact} onChange={(event) => setFact(event.target.value)}>
            {facts.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </Field>
        <Field label="Test">
          <select className={inputClass} value={op} onChange={(event) => setOp(event.target.value as ConditionOp)}>
            {OPS.map((item) => (
              <option key={item.op} value={item.op}>
                {item.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Value" hint="true/false, a number, text, or a comma-separated list for 'is one of'">
          <input className={inputClass} value={value} disabled={!takesValue(op)} onChange={(event) => setValue(event.target.value)} />
        </Field>
        <Field label="Points">
          <NumberInput value={points} min={-100} max={100} onChange={setPoints} />
        </Field>
        <Button type="button" variant="ghost" icon="add" disabled={!label.trim() || (takesValue(op) && !value.trim())} onClick={add}>
          Add
        </Button>
      </div>
    </div>
  )
}

function CustomFieldEditor({ fields, onChange }: { fields: CustomFieldDefinition[]; onChange: (fields: CustomFieldDefinition[]) => void }) {
  const [label, setLabel] = useState('')
  const [type, setType] = useState<CustomFieldType>('text')
  const [options, setOptions] = useState('')
  const key = slug(label).replace(/^r_/, 'f_')
  const add = () => {
    onChange([...fields, { key, label: label.trim(), type, options: type === 'select' ? options.split(',').map((o) => o.trim()).filter(Boolean) : [] }])
    setLabel('')
    setOptions('')
  }
  const duplicate = fields.some((field) => field.key === key)
  return (
    <div className="space-y-3">
      <ul className="divide-y divide-line rounded-sm border border-line">
        {fields.length === 0 && <li className="px-3 py-2.5 text-ink-subtle">No custom fields defined: leads keep whatever custom fields they arrive with.</li>}
        {fields.map((field, index) => (
          <li key={field.key} className="flex items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{field.label}</p>
              <p className="font-mono text-[11px] text-ink-subtle">
                {field.key} · {field.type}
                {field.options.length > 0 && `: ${field.options.join(', ')}`}
              </p>
            </div>
            <Button type="button" variant="danger" size="sm" icon="delete" aria-label={`Remove ${field.label}`} onClick={() => onChange(fields.filter((_, i) => i !== index))} />
          </li>
        ))}
      </ul>
      <div className="grid gap-2 rounded-sm bg-canvas p-3 sm:grid-cols-[2fr_1fr_2fr_auto] sm:items-end">
        <Field label="New field">
          <input className={inputClass} placeholder="e.g. Rooms" value={label} maxLength={100} onChange={(event) => setLabel(event.target.value)} />
        </Field>
        <Field label="Type">
          <select className={inputClass} value={type} onChange={(event) => setType(event.target.value as CustomFieldType)}>
            {FIELD_TYPES.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </Field>
        <Field label="Options (select only)">
          <input className={inputClass} placeholder="buy, rent" value={options} disabled={type !== 'select'} onChange={(event) => setOptions(event.target.value)} />
        </Field>
        <Button type="button" variant="ghost" icon="add" disabled={!label.trim() || duplicate || (type === 'select' && !options.trim())} onClick={add}>
          Add
        </Button>
      </div>
    </div>
  )
}

function HoursGrid({ title, values, onChange }: { title: string; values: Record<PriorityName, number>; onChange: (values: Record<PriorityName, number>) => void }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold text-ink">{title}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PRIORITIES.map((priority) => (
          <Field key={priority} label={`${titleCase(priority)} (hours)`}>
            <NumberInput value={values[priority]} min={0.1} step={0.5} onChange={(next) => onChange({ ...values, [priority]: next })} />
          </Field>
        ))}
      </div>
    </div>
  )
}

function SettingsForm({ business }: { business: Business }) {
  const [config, setConfig] = useState<BusinessConfiguration>(business.configuration)
  const [fields, setFields] = useState<CustomFieldDefinition[]>(business.custom_field_definitions)
  const [closed, setClosed] = useState(business.configuration.closed_statuses.join(', '))
  const [statusHours, setStatusHours] = useState(
    Object.entries(business.configuration.follow_up.status_interval_hours)
      .map(([status, hours]) => `${status}: ${hours}`)
      .join('\n'),
  )
  const update = useUpdateSettings(business.id)
  const rescore = useRescore(business.id)
  const [toast, setToast] = useState<string | null>(null)
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 3200)
    return () => clearTimeout(timer)
  }, [toast])

  const save = async () => {
    const statusIntervals = Object.fromEntries(
      statusHours
        .split('\n')
        .map((line) => line.split(':').map((part) => part.trim()))
        .filter(([status, hours]) => status && hours)
        .map(([status, hours]) => [status, Number(hours)]),
    )
    const configuration: BusinessConfiguration = {
      ...config,
      closed_statuses: closed.split(',').map((status) => status.trim()).filter(Boolean),
      follow_up: { ...config.follow_up, status_interval_hours: statusIntervals },
    }
    await update.mutateAsync({ configuration, custom_field_definitions: fields })
    const result = await rescore.mutateAsync({})
    setToast(`Saved. ${result.changed} of ${result.total} leads rescored.`)
  }
  const busy = update.isPending || rescore.isPending
  const error = update.error ?? rescore.error
  const set = <K extends keyof BusinessConfiguration>(key: K, value: BusinessConfiguration[K]) => setConfig({ ...config, [key]: value })

  return (
    <Stagger className="space-y-5" step={0.07}>
      <Card>
        <CardHeader title="Scoring rules" icon="calculate" />
        <div className="space-y-4 p-5 text-[13px]">
          <p className="text-ink-muted">
            Every lead starts at the starting score; each matching rule adds or subtracts its points (0–100). When a lead has an AI score, the two are blended
            by the AI weight.
          </p>
          <div className="grid max-w-md grid-cols-2 gap-3">
            <Field label="Starting score">
              <NumberInput value={config.scoring.base_score} min={0} max={100} onChange={(next) => set('scoring', { ...config.scoring, base_score: next })} />
            </Field>
            <Field label="AI weight (0–1)">
              <NumberInput value={config.scoring.ai_weight} min={0} max={1} step={0.05} onChange={(next) => set('scoring', { ...config.scoring, ai_weight: next })} />
            </Field>
          </div>
          <RuleEditor rules={config.scoring.rules} customKeys={fields.map((field) => field.key)} onChange={(rules) => set('scoring', { ...config.scoring, rules })} />
        </div>
      </Card>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Priority" icon="flag" />
          <div className="space-y-3 p-5 text-[13px]">
            <p className="text-ink-muted">The lowest score for each priority. Below medium is low. A priority picked by hand stays until the score changes.</p>
            <div className="grid grid-cols-3 gap-3">
              {(['critical', 'high', 'medium'] as const).map((name) => (
                <Field key={name} label={titleCase(name)}>
                  <NumberInput value={config.priority[name]} min={0} max={100} onChange={(next) => set('priority', { ...config.priority, [name]: next })} />
                </Field>
              ))}
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Pipeline" icon="view_kanban" />
          <div className="space-y-3 p-5 text-[13px]">
            <Field label="Closed statuses (comma-separated)" hint="Closed leads need no follow-up and are left out of open-lead counts.">
              <input className={inputClass} value={closed} onChange={(event) => setClosed(event.target.value)} />
            </Field>
            <Field label="Country code for phone numbers" hint="Two letters, e.g. IL or US. Local numbers (050-…) are stored in international format for it.">
              <input
                className={`${inputClass} w-24 font-mono uppercase`}
                value={config.phone_region ?? ''}
                maxLength={2}
                onChange={(event) => set('phone_region', event.target.value.trim().toUpperCase() || null)}
                placeholder="IL"
              />
            </Field>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Follow-up timing" icon="event_upcoming" />
        <div className="space-y-4 p-5 text-[13px]">
          <HoursGrid
            title="First response: hours after a new lead arrives"
            values={config.follow_up.first_response_hours}
            onChange={(values) => set('follow_up', { ...config.follow_up, first_response_hours: values })}
          />
          <HoursGrid
            title="After contact: hours until the next follow-up"
            values={config.follow_up.interval_hours}
            onChange={(values) => set('follow_up', { ...config.follow_up, interval_hours: values })}
          />
          <Field label="Per-status overrides (one 'status: hours' per line)">
            <textarea className={`${inputClass} h-auto py-2 font-mono`} rows={3} value={statusHours} onChange={(event) => setStatusHours(event.target.value)} />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Custom fields" icon="tune" />
        <div className="space-y-3 p-5 text-[13px]">
          <p className="text-ink-muted">Typed fields are checked on every lead save and import. Scoring rules can test them as custom_fields.&lt;key&gt;.</p>
          <CustomFieldEditor fields={fields} onChange={setFields} />
        </div>
      </Card>

      {error && <ErrorState message={error.message} />}
      <div className="flex justify-end">
        <Button type="button" icon={busy ? 'progress_activity' : 'save'} disabled={busy} onClick={() => void save().catch(() => undefined)}>
          {busy ? 'Saving…' : 'Save and rescore leads'}
        </Button>
      </div>
      <Toast show={toast != null}>{toast}</Toast>
    </Stagger>
  )
}

export function SettingsPage() {
  const { businessId = '' } = useParams()
  const business = useBusiness(businessId)
  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Icon name="settings" /> Settings
        </h1>
        <p className="text-ink-muted">Your WhatsApp number, and how leads are scored, prioritized and followed up.</p>
      </div>
      <WhatsAppSettings businessId={businessId} />
      {business.isPending && <Skeleton className="h-96" />}
      {business.isError && <ErrorState message={business.error.message} onRetry={() => void business.refetch()} />}
      {business.data && <SettingsForm business={business.data} key={business.data.id} />}
    </div>
  )
}
