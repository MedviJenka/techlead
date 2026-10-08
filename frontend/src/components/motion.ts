import type { Variants } from 'motion/react'

export const spring = { type: 'spring', stiffness: 380, damping: 30 } as const

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
}

export function scoreTone(score: number) {
  if (score >= 80) return { bar: 'bg-hot', text: 'text-hot' }
  if (score >= 50) return { bar: 'bg-primary', text: 'text-primary' }
  return { bar: 'bg-ink-subtle', text: 'text-ink-muted' }
}
