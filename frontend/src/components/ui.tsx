import {
  AnimatePresence,
  animate,
  motion,
  useInView,
  useMotionValue,
  useTransform,
  type HTMLMotionProps,
} from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { initials, isHot, titleCase } from './leadDisplay'
import { fadeUp, scoreTone, spring } from './motion'

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(' ')


/* ---------- Icons ---------- */

export function Icon({ name, className, fill }: { name: string; className?: string; fill?: boolean }) {
  return (
    <span className={cx('icon', fill && 'icon-fill', className)} aria-hidden="true">
      {name}
    </span>
  )
}

export function Sparkle({ className }: { className?: string }) {
  return <Icon name="auto_awesome" fill className={cx('animate-sparkle text-ai', className)} />
}

export function Logo({ size = 'md' }: { size?: 'md' | 'lg' }) {
  return (
    <span className="flex items-center gap-2">
      <motion.span
        whileHover={{ rotate: -12, scale: 1.08 }}
        transition={spring}
        className={cx('flex items-center justify-center rounded-sm bg-primary text-white', size === 'lg' ? 'size-10' : 'size-8')}
      >
        <Icon name="bolt" fill className={size === 'lg' ? 'text-2xl!' : ''} />
      </motion.span>
      <span className={cx('font-display font-extrabold tracking-tight', size === 'lg' ? 'text-2xl' : 'text-lg')}>Techlead</span>
    </span>
  )
}

/* ---------- Layout motion ---------- */


export function Stagger({
  children,
  className,
  delay = 0,
  step = 0.06,
  as = 'div',
}: {
  children: ReactNode
  className?: string
  delay?: number
  step?: number
  as?: 'div' | 'ul' | 'ol' | 'tbody'
}) {
  const Component = motion[as]
  return (
    <Component
      className={className}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: step, delayChildren: delay } } }}
    >
      {children}
    </Component>
  )
}

export function Reveal({ className, ...props }: HTMLMotionProps<'div'>) {
  return <motion.div variants={fadeUp} className={className} {...props} />
}

/* ---------- Surfaces ---------- */

export function Card({
  className,
  interactive,
  children,
  ...props
}: HTMLMotionProps<'section'> & { interactive?: boolean }) {
  return (
    <motion.section
      variants={fadeUp}
      whileHover={interactive ? { y: -3, boxShadow: 'var(--shadow-lift)' } : undefined}
      transition={spring}
      className={cx('rounded-md border border-line bg-surface', className)}
      {...props}
    >
      {children}
    </motion.section>
  )
}

export function CardHeader({ title, action, icon }: { title: ReactNode; action?: ReactNode; icon?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
      <h2 className="flex items-center gap-2 text-[15px] font-bold">
        {icon && <Icon name={icon} className="text-ink-subtle" />}
        {title}
      </h2>
      {action}
    </div>
  )
}

/* ---------- Buttons ---------- */

const buttonVariants = {
  primary: 'bg-primary text-white hover:bg-primary-hover shadow-sm',
  ghost: 'border border-line bg-transparent text-ink hover:bg-surface hover:border-ink-subtle/50',
  ai: 'bg-ai text-white hover:bg-ai/90 shadow-sm shadow-ai/30',
  subtle: 'text-ink-muted hover:bg-ink/5 hover:text-ink',
  danger: 'text-danger hover:bg-danger/8',
}

export function Button({
  variant = 'primary',
  icon,
  className,
  children,
  size = 'md',
  ...props
}: HTMLMotionProps<'button'> & {
  variant?: keyof typeof buttonVariants
  icon?: string
  size?: 'sm' | 'md'
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      transition={spring}
      className={cx(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-40',
        size === 'md' ? 'h-9 px-3.5 text-sm' : 'h-7 px-2.5 text-xs',
        buttonVariants[variant],
        className,
      )}
      {...props}
    >
      {icon && <Icon name={icon} className={size === 'sm' ? 'text-base!' : 'text-lg!'} />}
      {children as ReactNode}
    </motion.button>
  )
}

/* ---------- Data display ---------- */

/** Counts up from 0 when it scrolls into view, and tweens between later values. */
export function AnimatedNumber({ value, decimals = 0, className }: { value: number; decimals?: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const count = useMotionValue(0)
  const text = useTransform(count, (latest) =>
    latest.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }),
  )
  useEffect(() => {
    if (!inView) return
    const controls = animate(count, value, { duration: 1.1, ease: [0.16, 1, 0.3, 1] })
    return () => controls.stop()
  }, [count, inView, value])
  return (
    <motion.span ref={ref} className={cx('font-mono tabular-nums', className)}>
      {text}
    </motion.span>
  )
}


export function ScoreMeter({ score, wide }: { score: number | null; wide?: boolean }) {
  if (score == null) return <span className="font-mono text-ink-subtle">—</span>
  const tone = scoreTone(score)
  return (
    <div className={cx('flex items-center gap-2', wide ? 'w-40' : 'w-24')}>
      <span className={cx('w-7 font-mono text-[13px] font-medium tabular-nums', tone.text)}>{score}</span>
      <div className="h-1 flex-1 overflow-hidden rounded-full bg-line">
        <motion.div
          className={cx('h-full rounded-full', tone.bar)}
          initial={{ width: 0 }}
          whileInView={{ width: `${score}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
        />
      </div>
    </div>
  )
}

const STATUS_DOT: Record<string, string> = {
  new: 'bg-sky-500',
  contacted: 'bg-primary',
  qualified: 'bg-success',
  proposal: 'bg-ai',
  proposal_sent: 'bg-ai',
  negotiation: 'bg-ai',
  won: 'bg-success',
  lost: 'bg-danger',
  inactive: 'bg-ink-subtle',
}

export function StatusChip({ status }: { status: string }) {
  const dot = STATUS_DOT[status.toLowerCase()] ?? 'bg-warning'
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-muted">
      <span className={cx('size-1.5 rounded-full', dot)} />
      {titleCase(status)}
    </span>
  )
}

export function PriorityFlag({ priority }: { priority: string | null }) {
  if (!priority) return <span className="text-ink-subtle">—</span>
  const hot = isHot(priority)
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        hot ? 'bg-hot-surface text-hot' : 'text-ink-muted',
      )}
    >
      <Icon name="flag" fill={hot} className={cx('text-sm!', priority === 'critical' && 'animate-pulse')} />
      {titleCase(priority)}
    </span>
  )
}

const SOURCE_ICON: Record<string, string> = {
  whatsapp: 'chat',
  website: 'language',
  web: 'language',
  email: 'mail',
  phone: 'call',
  referral: 'group',
  facebook: 'thumb_up',
  instagram: 'photo_camera',
  google_ads: 'ads_click',
}

export function SourceChip({ source }: { source: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-line bg-canvas px-1.5 py-0.5 font-mono text-[11px] text-ink-muted">
      <Icon name={SOURCE_ICON[source.toLowerCase()] ?? 'input'} className="text-[13px]!" />
      {source}
    </span>
  )
}

const AVATAR_TONES = [
  'bg-primary-soft text-primary',
  'bg-ai-surface text-ai',
  'bg-hot-surface text-hot',
  'bg-amber-50 text-warning',
  'bg-sky-50 text-sky-700',
]

export function Avatar({ name, size = 'md', hot }: { name: string; size?: 'sm' | 'md' | 'lg'; hot?: boolean }) {
  const tone = AVATAR_TONES[[...name].reduce((sum, c) => sum + c.charCodeAt(0), 0) % AVATAR_TONES.length]
  const dims = { sm: 'size-7 text-[11px]', md: 'size-9 text-xs', lg: 'size-14 text-lg' }[size]
  return (
    <span className="relative inline-flex shrink-0">
      {hot && <span className="absolute inset-0 animate-ping-slow rounded-full bg-hot/40" />}
      <span className={cx('relative inline-flex items-center justify-center rounded-full font-display font-bold', dims, tone)}>
        {initials(name)}
      </span>
    </span>
  )
}

export function PulseDot({ tone = 'bg-success' }: { tone?: string }) {
  return (
    <span className="relative inline-flex size-2">
      <span className={cx('absolute inset-0 animate-ping-slow rounded-full', tone)} />
      <span className={cx('relative size-2 rounded-full', tone)} />
    </span>
  )
}

/* ---------- AI ---------- */

export function AiTag({ label = 'AI' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-ai/10 px-2 py-0.5 font-mono text-[11px] font-medium text-ai">
      <Sparkle className="text-[13px]!" />
      {label}
    </span>
  )
}

/** Advice from an agent: violet surface, sparkle tag, animated gradient edge. */
export function AiCard({
  title,
  children,
  why,
  meta,
  className,
}: {
  title: ReactNode
  children: ReactNode
  why?: ReactNode
  meta?: ReactNode
  className?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <motion.section variants={fadeUp} className={cx('ai-glow rounded-lg p-px', className)}>
      <div className="relative overflow-hidden rounded-[13px] bg-ai-surface p-5">
        <div className="pointer-events-none absolute -top-16 -right-10 size-40 animate-float rounded-full bg-ai/10 blur-2xl" />
        <div className="relative mb-3 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold text-ink">
            {title}
            <AiTag />
          </h2>
          {meta && <span className="font-mono text-[11px] text-ink-subtle">{meta}</span>}
        </div>
        <div className="relative text-ink">{children}</div>
        {why && (
          <div className="relative mt-3">
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              className="inline-flex items-center gap-1 text-xs font-medium text-ai hover:underline"
            >
              Why?
              <motion.span animate={{ rotate: open ? 180 : 0 }} className="inline-flex">
                <Icon name="expand_more" className="text-base!" />
              </motion.span>
            </button>
            <AnimatePresence initial={false}>
              {open && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="mt-2 rounded-sm border border-ai/20 bg-surface/70 p-3 text-xs text-ink-muted">{why}</div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.section>
  )
}

/* ---------- States ---------- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('skeleton rounded-sm', className)} />
}

export function EmptyState({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center gap-3 px-6 py-12 text-center"
    >
      <span className="flex size-12 animate-float items-center justify-center rounded-full bg-primary-soft text-primary">
        <Icon name={icon} className="text-2xl!" />
      </span>
      <p className="font-display text-[15px] font-bold">{title}</p>
      {children}
    </motion.div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <motion.div
      role="alert"
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: [0, -6, 6, -3, 3, 0] }}
      transition={{ duration: 0.45 }}
      className="flex items-center gap-3 rounded-md border border-danger/25 bg-danger/5 px-4 py-3 text-sm text-danger"
    >
      <Icon name="error" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button variant="ghost" size="sm" icon="refresh" onClick={onRetry}>
          Retry
        </Button>
      )}
    </motion.div>
  )
}

export function Toast({ show, children }: { show: boolean; children: ReactNode }) {
  // Portaled: a fixed element inside a transformed (animated) ancestor would be positioned against that ancestor.
  return createPortal(
    <AnimatePresence>
      {show && (
        <motion.div
          role="status"
          initial={{ opacity: 0, y: 24, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.97 }}
          transition={spring}
          className="fixed right-6 bottom-6 z-50 flex items-center gap-2 rounded-md bg-ink px-4 py-3 text-sm text-white shadow-lift"
        >
          <Icon name="check_circle" fill className="text-success" />
          {children}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
