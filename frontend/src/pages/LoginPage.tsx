import { motion } from 'motion/react'
import { useState } from 'react'

import { signInWithGoogle } from '../auth/supabase'
import { AiTag, Avatar, ErrorState, Icon, Logo, PriorityFlag, ScoreMeter, Stagger, StatusChip, Reveal } from '../components/ui'
import { spring } from '../components/motion'

const VALUES = [
  { icon: 'local_fire_department', text: 'Never miss a hot lead' },
  { icon: 'auto_awesome', text: 'AI-drafted follow-ups you approve' },
  { icon: 'timeline', text: "Every lead's story in one timeline" },
]

function PreviewStack() {
  return (
    <div className="relative mt-12 hidden h-56 max-w-md lg:block" aria-hidden="true">
      <motion.div
        initial={{ opacity: 0, y: 30, rotate: -6 }}
        animate={{ opacity: 1, y: 0, rotate: -4 }}
        transition={{ delay: 0.6, ...spring }}
        className="absolute top-8 left-10 w-80 animate-float rounded-md border border-line bg-surface p-4 shadow-pop [animation-delay:-3s]"
      >
        <div className="flex items-center gap-3">
          <Avatar name="Marcus Vance" />
          <div className="flex-1">
            <p className="font-semibold">Marcus Vance</p>
            <p className="text-xs text-ink-subtle">SunPower Installers</p>
          </div>
          <StatusChip status="contacted" />
        </div>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 40, rotate: 4 }}
        animate={{ opacity: 1, y: 0, rotate: 1.5 }}
        transition={{ delay: 0.8, ...spring }}
        className="absolute top-20 left-0 w-96 animate-float rounded-md border border-line bg-surface p-4 shadow-lift"
      >
        <div className="flex items-center gap-3">
          <Avatar name="Dana Levi" hot />
          <div className="flex-1">
            <p className="font-semibold">Dana Levi</p>
            <p className="text-xs text-ink-subtle">Levi Roofing Ltd</p>
          </div>
          <PriorityFlag priority="critical" />
        </div>
        <div className="mt-3 flex items-center justify-between">
          <ScoreMeter score={91} wide />
          <span className="font-mono text-[11px] text-hot">no contact · 3d</span>
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-sm bg-ai-surface px-3 py-2 text-xs">
          <AiTag />
          Call today: ready to sign a 12kW system.
        </div>
      </motion.div>
    </div>
  )
}

export function LoginPage() {
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onClick() {
    setError(null)
    setPending(true)
    const { error } = await signInWithGoogle()
    if (error) {
      setError(error.message)
      setPending(false)
    }
  }

  return (
    <div className="relative grid min-h-screen overflow-hidden lg:grid-cols-[1.15fr_1fr]">
      <div className="pointer-events-none absolute -top-40 -left-40 size-[480px] animate-float rounded-full bg-primary/10 blur-3xl" />
      <div className="pointer-events-none absolute -right-32 bottom-0 size-[420px] animate-float rounded-full bg-ai/10 blur-3xl [animation-delay:-2s]" />

      <Stagger className="relative flex flex-col justify-center px-8 py-12 lg:px-20" step={0.1}>
        <Reveal>
          <Logo />
        </Reveal>
        <Reveal>
          <h1 className="mt-10 max-w-xl text-4xl leading-[1.1] font-extrabold tracking-tight lg:text-5xl">
            Your business already has leads.{' '}
            <span className="bg-gradient-to-r from-primary via-ai to-hot bg-[length:200%_auto] bg-clip-text text-transparent animate-gradient">
              We make sure you do not lose them.
            </span>
          </h1>
        </Reveal>
        <ul className="mt-8 space-y-3">
          {VALUES.map((value) => (
            <motion.li key={value.text} variants={{ hidden: { opacity: 0, x: -12 }, show: { opacity: 1, x: 0 } }} className="flex items-center gap-3 text-[15px]">
              <span className="flex size-8 items-center justify-center rounded-sm bg-primary-soft text-primary">
                <Icon name={value.icon} fill />
              </span>
              {value.text}
            </motion.li>
          ))}
        </ul>
        <PreviewStack />
      </Stagger>

      <div className="relative flex items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: 0.2, ...spring }}
          className="w-full max-w-sm rounded-lg border border-line bg-surface p-8 shadow-lift"
        >
          <motion.span
            initial={{ rotate: -90, scale: 0 }}
            animate={{ rotate: 0, scale: 1 }}
            transition={{ delay: 0.45, type: 'spring', stiffness: 260, damping: 14 }}
            className="flex size-12 items-center justify-center rounded-md bg-primary text-white"
          >
            <Icon name="bolt" fill className="text-3xl!" />
          </motion.span>
          <h2 className="mt-5 text-2xl font-bold">Sign in to your workspace</h2>
          <p className="mt-1.5 text-ink-muted">Use your Google account to continue.</p>
          <motion.button
            type="button"
            onClick={onClick}
            disabled={pending}
            whileHover={{ y: -2, boxShadow: 'var(--shadow-lift)' }}
            whileTap={{ scale: 0.97 }}
            transition={spring}
            className="mt-7 flex h-11 w-full items-center justify-center gap-3 rounded-sm border border-line bg-surface font-medium disabled:opacity-60"
          >
            {pending ? (
              <motion.span animate={{ rotate: 360 }} transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }} className="inline-flex">
                <Icon name="progress_activity" className="text-primary" />
              </motion.span>
            ) : (
              <GoogleMark />
            )}
            {pending ? 'Redirecting…' : 'Continue with Google'}
          </motion.button>
          {error && (
            <div className="mt-4">
              <ErrorState message={error} />
            </div>
          )}
          <p className="mt-6 text-center text-xs text-ink-subtle">
            By continuing you agree to the Terms of Service and Privacy Policy.
          </p>
        </motion.div>
      </div>
    </div>
  )
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-5" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.2-.1-2.3-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.2-.1-2.3-.4-3.5z" />
    </svg>
  )
}
