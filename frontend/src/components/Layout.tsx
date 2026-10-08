import type { Session } from '@supabase/supabase-js'
import { useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useMatch, useNavigate } from 'react-router'

import { useBusiness, useHealth, useMe } from '../api/hooks'
import { supabase, useSession } from '../auth/supabase'
import { LoginPage } from '../pages/LoginPage'
import { initials } from './leadDisplay'
import { Icon, Logo, PulseDot, Sparkle } from './ui'
import { spring } from './motion'

function HealthBadge() {
  const { data, isPending, isError } = useHealth()
  const healthy = data?.status === 'ok'
  const label = isPending ? 'Checking…' : healthy ? 'API online' : isError ? 'API offline' : 'Database unavailable'
  const tone = isPending ? 'bg-ink-subtle' : healthy ? 'bg-success' : 'bg-danger'

  return (
    <span className="flex items-center gap-2 text-xs text-ink-muted" role="status">
      <PulseDot tone={tone} />
      {label}
    </span>
  )
}

type NavItem = { to: string; label: string; icon: string; end?: boolean } | { label: string; icon: string; soon: true }

function navItems(businessId: string | null): NavItem[] {
  const base = businessId ? `/businesses/${businessId}` : null
  return [
    base ? { to: base, label: 'Dashboard', icon: 'space_dashboard', end: true } : { label: 'Dashboard', icon: 'space_dashboard', soon: true },
    base ? { to: `${base}/leads`, label: 'Leads', icon: 'groups' } : { label: 'Leads', icon: 'groups', soon: true },
    { label: 'Follow-ups', icon: 'outgoing_mail', soon: true },
    { label: 'Assistant', icon: 'auto_awesome', soon: true },
    base ? { to: `${base}/settings`, label: 'Settings', icon: 'settings' } : { label: 'Settings', icon: 'settings', soon: true },
  ]
}

function SideNav({ businessId }: { businessId: string | null }) {
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {navItems(businessId).map((item) =>
        'soon' in item ? (
          <span key={item.label} className="flex h-9 items-center gap-3 rounded-sm px-3 text-ink-subtle" title="Coming soon">
            <Icon name={item.icon} />
            {item.label}
            <span className="ml-auto rounded-full bg-canvas px-1.5 py-px font-mono text-[10px]">soon</span>
          </span>
        ) : (
          <NavLink key={item.to} to={item.to} end={item.end} className="relative">
            {({ isActive }) => (
              <span
                className={`relative flex h-9 items-center gap-3 rounded-sm px-3 font-medium transition-colors ${isActive ? 'text-primary' : 'text-ink-muted hover:text-ink'}`}
              >
                {isActive && (
                  <motion.span
                    layoutId="nav-active"
                    transition={spring}
                    className="absolute inset-0 rounded-sm bg-primary-soft"
                  />
                )}
                <Icon name={item.icon} fill={isActive} className="relative" />
                <span className="relative">{item.label}</span>
              </span>
            )}
          </NavLink>
        ),
      )}
    </nav>
  )
}

function BusinessSwitcher({ businessId }: { businessId: string | null }) {
  const business = useBusiness(businessId ?? '', { enabled: Boolean(businessId) })
  if (!businessId) return null
  const name = business.data?.name ?? '…'
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2.5 rounded-md border border-line bg-canvas/60 p-2.5"
    >
      <span className="flex size-8 items-center justify-center rounded-sm bg-ink font-display text-xs font-bold text-white">
        {initials(name)}
      </span>
      <div className="min-w-0">
        <p className="truncate text-[13px] font-semibold">{name}</p>
        <p className="truncate text-xs text-ink-subtle">{business.data?.industry ?? 'Business'}</p>
      </div>
    </motion.div>
  )
}

function UserMenu({ session }: { session: Session }) {
  const queryClient = useQueryClient()
  const email = session.user.email ?? 'Signed in'

  async function signOut() {
    await supabase.auth.signOut()
    queryClient.clear()
  }

  return (
    <div className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-full bg-primary-soft font-display text-xs font-bold text-primary">
        {initials(email)}
      </span>
      <span className="min-w-0 flex-1 truncate text-xs text-ink-muted" title={email}>
        {email}
      </span>
      <button
        type="button"
        onClick={signOut}
        aria-label="Sign out"
        className="rounded-sm p-1.5 text-ink-subtle transition hover:bg-ink/5 hover:text-danger"
      >
        <Icon name="logout" />
      </button>
    </div>
  )
}

function Sidebar({ session, businessId }: { session: Session; businessId: string | null }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col gap-5 border-r border-line bg-surface px-3 py-4 md:flex">
      <Link to="/" className="px-2">
        <Logo />
      </Link>
      <BusinessSwitcher businessId={businessId} />
      <SideNav businessId={businessId} />
      <div className="mt-auto space-y-3 border-t border-line px-1 pt-4">
        <HealthBadge />
        <UserMenu session={session} />
      </div>
    </aside>
  )
}

function Breadcrumb() {
  const { pathname } = useLocation()
  const parts = pathname.includes('/leads/')
    ? ['Leads', 'Lead']
    : pathname.endsWith('/leads')
      ? ['Leads']
      : pathname.endsWith('/settings')
        ? ['Settings']
        : pathname.startsWith('/businesses')
          ? ['Dashboard']
          : ['Welcome']
  return (
    <nav aria-label="Breadcrumb" className="hidden items-center gap-1.5 text-[13px] text-ink-subtle lg:flex">
      <Icon name="home" className="text-base!" />
      {parts.map((part, index) => (
        <motion.span
          key={`${part}-${index}`}
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          className={`flex items-center gap-1.5 ${index === parts.length - 1 ? 'font-medium text-ink' : ''}`}
        >
          <span className="text-line">/</span>
          {part}
        </motion.span>
      ))}
    </nav>
  )
}

function GlobalSearch({ businessId }: { businessId: string | null }) {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) {
        event.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!businessId) return <div className="flex-1" />

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const q = String(new FormData(event.currentTarget).get('q') ?? '').trim()
    navigate(`/businesses/${businessId}/leads${q ? `?q=${encodeURIComponent(q)}` : ''}`)
    input.current?.blur()
  }

  return (
    <motion.form
      onSubmit={submit}
      role="search"
      animate={{ maxWidth: focused ? 560 : 420 }}
      transition={spring}
      className="relative flex-1"
    >
      <Icon name="search" className="absolute top-1/2 left-3 -translate-y-1/2 text-ink-subtle" />
      <input
        ref={input}
        name="q"
        aria-label="Search leads"
        maxLength={100}
        placeholder="Search leads by name, email, phone, company"
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="h-9 w-full rounded-sm border border-line bg-canvas/70 pr-10 pl-10 text-sm transition placeholder:text-ink-subtle focus:border-primary focus:bg-surface focus:ring-3 focus:ring-primary/15 focus:outline-none"
      />
      <kbd className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded-sm border border-line bg-surface px-1.5 font-mono text-[11px] text-ink-subtle">
        /
      </kbd>
    </motion.form>
  )
}

function TopBar({ businessId }: { businessId: string | null }) {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-line bg-canvas/80 px-4 backdrop-blur-md md:px-6">
      <Link to="/" className="md:hidden">
        <Logo />
      </Link>
      <Breadcrumb />
      <GlobalSearch businessId={businessId} />
      {businessId && (
        <Link
          to={`/businesses/${businessId}/leads?import=1`}
          className="hidden h-9 items-center gap-1.5 rounded-sm border border-line px-3.5 text-sm font-medium transition hover:border-ink-subtle/50 hover:bg-surface sm:inline-flex"
        >
          <Icon name="upload" className="text-lg!" />
          Import leads
        </Link>
      )}
      <span
        className="hidden h-9 cursor-not-allowed items-center gap-1.5 rounded-sm bg-ai/10 px-3.5 text-sm font-medium text-ai lg:inline-flex"
        title="The assistant is coming soon"
      >
        <Sparkle className="text-lg!" />
        Ask AI
      </span>
    </header>
  )
}

function MobileTabs({ businessId }: { businessId: string | null }) {
  const items = navItems(businessId).filter((item) => !('soon' in item))
  if (!items.length) return null
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 backdrop-blur md:hidden" aria-label="Main">
      {items.map(
        (item) =>
          'to' in item && (
            <NavLink key={item.to} to={item.to} end={item.end} className="relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]">
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="tab-active" className="absolute inset-x-6 top-0 h-0.5 rounded-full bg-primary" />}
                  <Icon name={item.icon} fill={isActive} className={isActive ? 'text-primary' : 'text-ink-subtle'} />
                  <span className={isActive ? 'font-medium text-primary' : 'text-ink-muted'}>{item.label}</span>
                </>
              )}
            </NavLink>
          ),
      )}
    </nav>
  )
}

function Splash() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <motion.div animate={{ scale: [1, 1.06, 1], opacity: [0.7, 1, 0.7] }} transition={{ duration: 1.6, repeat: Infinity }}>
        <Logo size="lg" />
      </motion.div>
    </div>
  )
}

function Shell({ session }: { session: Session }) {
  const me = useMe()
  const match = useMatch('/businesses/:businessId/*')
  const businessId = match?.params.businessId ?? me.data?.business_id ?? null
  const { pathname } = useLocation()

  return (
    <div className="min-h-screen">
      <Sidebar session={session} businessId={businessId} />
      <div className="md:pl-60">
        <TopBar businessId={businessId} />
        <main className="mx-auto max-w-[1280px] px-4 pt-6 pb-24 md:px-6 md:pb-10">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <Outlet />
          </motion.div>
        </main>
      </div>
      <MobileTabs businessId={businessId} />
    </div>
  )
}

export function Layout() {
  const session = useSession()
  if (session === undefined) return <Splash />
  return session ? <Shell session={session} /> : <LoginPage />
}
