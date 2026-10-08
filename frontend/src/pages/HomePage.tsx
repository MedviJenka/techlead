import { AnimatePresence, motion } from 'motion/react'
import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'

import { useCreateBusiness, useMe } from '../api/hooks'
import { inputClass } from '../components/leadDisplay'
import { Button, ErrorState, Icon, Reveal, Skeleton, Stagger } from '../components/ui'
import { spring } from '../components/motion'

const slugify = (value: string) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

const INDUSTRIES = ['Solar energy', 'Real estate', 'Clinic', 'Agency', 'Education', 'Insurance']

export function HomePage() {
  const me = useMe()
  if (me.isPending)
    return (
      <div className="mx-auto max-w-lg space-y-4 pt-10">
        <Skeleton className="h-8 w-60" />
        <Skeleton className="h-80" />
      </div>
    )
  if (me.isError) return <ErrorState message={me.error.message} onRetry={() => void me.refetch()} />
  // A user belongs to one business: go straight to it, or offer to create it.
  if (me.data.business_id) return <Navigate to={`/businesses/${me.data.business_id}`} replace />
  return <CreateBusiness />
}

function CreateBusiness() {
  const navigate = useNavigate()
  const createBusiness = useCreateBusiness()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [industry, setIndustry] = useState('')
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone)
  const effectiveSlug = slug || slugify(name)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    createBusiness.mutate(
      { name, slug: effectiveSlug, industry: industry || null, timezone },
      { onSuccess: (business) => navigate(`/businesses/${business.id}`) },
    )
  }

  return (
    <Stagger className="mx-auto max-w-lg pt-6" step={0.08}>
      <Reveal className="text-center">
        <motion.span
          initial={{ scale: 0, rotate: -45 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 260, damping: 14 }}
          className="mx-auto flex size-14 items-center justify-center rounded-lg bg-primary-soft text-primary"
        >
          <Icon name="storefront" fill className="text-3xl!" />
        </motion.span>
        <p className="mt-4 font-mono text-[11px] tracking-widest text-ink-subtle uppercase">Step 1 of 1</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight">Create your business</h1>
        <p className="mt-1 text-ink-muted">You'll be the owner. You can invite your team later.</p>
      </Reveal>

      <Reveal>
        <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-lg border border-line bg-surface p-6 shadow-pop">
          <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
            Business name
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Solar" required autoFocus />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
            Slug
            <input className={`${inputClass} font-mono`} value={slug} placeholder={slugify(name) || 'acme-solar'} onChange={(e) => setSlug(e.target.value)} />
            <AnimatePresence>
              {effectiveSlug && (
                <motion.span initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="font-mono text-[11px] font-normal text-ink-subtle">
                  techlead.app/
                  <motion.span key={effectiveSlug} initial={{ color: '#0e7c66' }} animate={{ color: '#14171f' }} transition={{ duration: 0.8 }}>
                    {effectiveSlug}
                  </motion.span>
                </motion.span>
              )}
            </AnimatePresence>
          </label>
          <div className="flex flex-col gap-1.5 text-xs font-medium text-ink-muted">
            Industry
            <div className="flex flex-wrap gap-1.5">
              {INDUSTRIES.map((option) => (
                <motion.button
                  key={option}
                  type="button"
                  whileTap={{ scale: 0.94 }}
                  transition={spring}
                  aria-pressed={industry === option}
                  onClick={() => setIndustry(industry === option ? '' : option)}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${industry === option ? 'border-primary bg-primary-soft text-primary' : 'border-line text-ink-muted hover:border-ink-subtle/50'}`}
                >
                  {option}
                </motion.button>
              ))}
            </div>
            <input className={inputClass} value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="Or type your own" aria-label="Industry" />
          </div>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink-muted">
            Timezone
            <input className={inputClass} value={timezone} onChange={(e) => setTimezone(e.target.value)} required />
          </label>

          {createBusiness.isError && <ErrorState message={createBusiness.error.message} />}

          <Button type="submit" disabled={createBusiness.isPending || !name} icon={createBusiness.isPending ? 'progress_activity' : 'rocket_launch'} className="w-full">
            {createBusiness.isPending ? 'Creating…' : 'Create business'}
          </Button>
        </form>
      </Reveal>
    </Stagger>
  )
}
