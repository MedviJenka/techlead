import { useParams } from 'react-router'

import { useBusiness } from '../api/hooks'

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm">{value}</dd>
    </div>
  )
}

export function BusinessPage() {
  const { businessId = '' } = useParams()
  const { data: business, isPending, isError, error } = useBusiness(businessId)

  if (isPending) return <p className="text-sm text-slate-600">Loading…</p>
  if (isError)
    return (
      <p className="text-sm text-rose-600" role="alert">
        {error.message}
      </p>
    )

  return (
    <section>
      <h1 className="text-2xl font-semibold">{business.name}</h1>
      <dl className="mt-6 grid grid-cols-2 gap-6 rounded-lg border border-slate-200 bg-white p-6 sm:grid-cols-4">
        <Field label="Slug" value={business.slug} />
        <Field label="Industry" value={business.industry ?? '—'} />
        <Field label="Timezone" value={business.timezone} />
        <Field label="Created" value={new Date(business.created_at).toLocaleString()} />
      </dl>
      <h2 className="mt-8 text-lg font-semibold">AI configuration</h2>
      <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-4 text-xs">
        {JSON.stringify(business.ai_configuration, null, 2)}
      </pre>
    </section>
  )
}
