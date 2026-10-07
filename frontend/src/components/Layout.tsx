import { Link, Outlet } from 'react-router'

import { useHealth } from '../api/hooks'

function HealthBadge() {
  const { data, isPending, isError } = useHealth()
  const healthy = data?.status === 'ok'
  const label = isPending ? 'Checking…' : healthy ? 'API online' : isError ? 'API offline' : 'Database unavailable'
  const color = isPending ? 'bg-slate-300' : healthy ? 'bg-emerald-500' : 'bg-rose-500'

  return (
    <span className="flex items-center gap-2 text-sm text-slate-600" role="status">
      <span className={`size-2 rounded-full ${color}`} aria-hidden="true" />
      {label}
    </span>
  )
}

export function Layout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Techlead
          </Link>
          <HealthBadge />
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
