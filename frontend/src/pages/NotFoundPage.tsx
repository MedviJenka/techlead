import { motion } from 'motion/react'
import { Link } from 'react-router'

import { Icon } from '../components/ui'

export function NotFoundPage() {
  return (
    <section className="flex flex-col items-center py-20 text-center">
      <motion.span
        animate={{ rotate: [0, -8, 8, -4, 0], y: [0, -6, 0] }}
        transition={{ duration: 2.4, repeat: Infinity, repeatDelay: 1 }}
        className="font-mono text-7xl font-medium text-line"
      >
        404
      </motion.span>
      <h1 className="mt-4 text-2xl font-bold">Page not found</h1>
      <p className="mt-1 text-ink-muted">This page does not exist, or it moved.</p>
      <Link to="/" className="mt-6 inline-flex h-9 items-center gap-1.5 rounded-sm bg-primary px-3.5 text-sm font-medium text-white hover:bg-primary-hover">
        <Icon name="home" className="text-lg!" /> Back home
      </Link>
    </section>
  )
}
