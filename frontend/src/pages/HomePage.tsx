import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router'

import { useCreateBusiness } from '../api/hooks'

const slugify = (value: string) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

const inputClass =
  'mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

export function HomePage() {
  const navigate = useNavigate()
  const createBusiness = useCreateBusiness()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [industry, setIndustry] = useState('')
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    createBusiness.mutate(
      { name, slug: slug || slugify(name), industry: industry || null, timezone },
      { onSuccess: (business) => navigate(`/businesses/${business.id}`) },
    )
  }

  return (
    <section className="max-w-lg">
      <h1 className="text-2xl font-semibold">Create a business</h1>
      <p className="mt-1 text-sm text-slate-600">Every business is an isolated tenant with its own leads and rules.</p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-lg border border-slate-200 bg-white p-6">
        <label className="block text-sm font-medium">
          Name
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="block text-sm font-medium">
          Slug
          <input
            className={inputClass}
            value={slug}
            placeholder={slugify(name) || 'acme-solar'}
            onChange={(e) => setSlug(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium">
          Industry
          <input className={inputClass} value={industry} onChange={(e) => setIndustry(e.target.value)} />
        </label>
        <label className="block text-sm font-medium">
          Timezone
          <input className={inputClass} value={timezone} onChange={(e) => setTimezone(e.target.value)} required />
        </label>

        {createBusiness.isError && (
          <p className="text-sm text-rose-600" role="alert">
            {createBusiness.error.message}
          </p>
        )}

        <button
          type="submit"
          disabled={createBusiness.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {createBusiness.isPending ? 'Creating…' : 'Create business'}
        </button>
      </form>
    </section>
  )
}
