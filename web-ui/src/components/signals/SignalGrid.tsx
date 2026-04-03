import type { ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AlertTriangle,
  Inbox,
  LoaderCircle,
  RefreshCcw,
  Search,
} from 'lucide-react'

import { SignalCard } from './SignalCard'
import { Heartbeat } from '../metrics/Heartbeat'
import type { SignalData } from '../../lib/contracts'

interface SignalGridProps {
  signals: SignalData[]
  totalSignalCount: number
  searchTerm: string
  loading: boolean
  isRefreshing: boolean
  error: string | null
  lastUpdated: string | null
  onRetry: () => void
  onSearch: (term: string) => void
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Awaiting first sync'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function SearchPanel({
  searchTerm,
  onSearch,
  disabled,
}: {
  searchTerm: string
  onSearch: (term: string) => void
  disabled: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="brutalist-card p-6 h-full flex flex-col justify-center bg-brand-accent/5 border-dashed border-brand-accent/30 hover:border-brand-accent/50 transition-all group"
    >
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="w-12 h-12 rounded-xl bg-brand-accent/10 flex items-center justify-center group-hover:scale-110 transition-transform">
          <Search className="w-6 h-6 text-brand-accent" />
        </div>
        <div>
          <h4 className="font-display font-bold text-lg">Scan Universe</h4>
          <p className="text-[10px] font-mono text-brand-text-dim text-wrap px-4 uppercase tracking-tighter mt-1 font-bold">
            Filter the live institutional sweep by ticker, company, or sector
          </p>
        </div>
        <div className="mt-4 w-full relative">
          <input
            aria-label="Filter signal grid"
            type="text"
            value={searchTerm}
            placeholder="PROMPT TICKER..."
            disabled={disabled}
            onChange={(event) => onSearch(event.target.value)}
            className="w-full bg-brand-bg border border-brand-border rounded-xl px-4 py-3 text-xs font-mono focus:border-brand-accent outline-none font-bold disabled:opacity-40 disabled:cursor-not-allowed"
          />
        </div>
      </div>
    </motion.div>
  )
}

function SignalGridStatus({
  icon,
  title,
  message,
  actionLabel,
  onAction,
}: {
  icon: ReactNode
  title: string
  message: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="brutalist-card p-8 border-dashed border-brand-border flex min-h-[280px] flex-col items-center justify-center gap-4 text-center xl:col-span-3"
    >
      <div className="w-14 h-14 rounded-2xl bg-white/5 flex items-center justify-center text-brand-accent">
        {icon}
      </div>
      <div className="space-y-2 max-w-md">
        <h3 className="font-display text-2xl font-black tracking-tight">{title}</h3>
        <p className="text-sm text-brand-text-dim leading-relaxed">{message}</p>
      </div>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-2 inline-flex items-center gap-2 rounded-xl border border-brand-accent/30 bg-brand-accent/10 px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest text-brand-accent transition-colors hover:border-brand-accent/60 hover:bg-brand-accent/15"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          {actionLabel}
        </button>
      ) : null}
    </motion.div>
  )
}

function SignalCardSkeleton({ index }: { index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.15 + index * 0.04 }}
      className={`brutalist-card p-6 min-h-[240px] ${index % 3 === 0 ? 'mt-4' : 'mt-0'}`}
    >
      <div className="animate-pulse space-y-5">
        <div className="flex justify-between items-start">
          <div className="space-y-3">
            <div className="h-6 w-28 rounded bg-white/10" />
            <div className="h-3 w-20 rounded bg-white/5" />
          </div>
          <div className="h-6 w-14 rounded bg-white/5" />
        </div>
        <div className="space-y-2">
          <div className="h-7 w-32 rounded bg-white/10" />
          <div className="h-3 w-16 rounded bg-white/5" />
        </div>
        <div className="space-y-3 pt-10">
          <div className="h-[2px] w-full rounded bg-white/5" />
          <div className="h-4 w-12 rounded bg-white/10" />
        </div>
      </div>
    </motion.div>
  )
}

export function SignalGrid({
  signals,
  totalSignalCount,
  searchTerm,
  loading,
  isRefreshing,
  error,
  lastUpdated,
  onRetry,
  onSearch,
}: SignalGridProps) {
  const hasSearch = searchTerm.trim().length > 0
  const isEmptyUniverse = !loading && totalSignalCount === 0
  const isEmptySearch = !loading && totalSignalCount > 0 && signals.length === 0

  return (
    <main className="p-8 pt-12">
      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          className={`brutalist-card p-6 border-l-4 ${
            error ? 'border-l-brand-rose' : 'border-l-brand-accent'
          }`}
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-brand-text-dim font-bold">
                Signal Lattice
              </p>
              <h2 className="font-display text-3xl font-black tracking-tight">
                Institutional sweep across the live multibagger feed
              </h2>
              <p className="max-w-2xl text-sm leading-relaxed text-brand-text-dim">
                The dashboard now consumes normalized contracts from the backend and
                keeps stale data visible when a refresh misses.
              </p>
            </div>

            <div className="min-w-[180px] rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <p className="font-mono text-[10px] uppercase tracking-widest text-brand-text-dim font-bold">
                Feed Status
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-widest ${
                    error
                      ? 'bg-brand-rose/10 text-brand-rose'
                      : loading
                        ? 'bg-brand-gold/10 text-brand-gold'
                        : 'bg-brand-accent/10 text-brand-accent'
                  }`}
                >
                  {loading ? (
                    <LoaderCircle className="h-3 w-3 animate-spin" />
                  ) : isRefreshing ? (
                    <RefreshCcw className="h-3 w-3 animate-spin" />
                  ) : null}
                  {loading ? 'Initializing' : isRefreshing ? 'Refreshing' : error ? 'Degraded' : 'Live'}
                </span>
              </div>
              <p className="mt-3 text-[11px] font-mono font-bold uppercase tracking-wide text-brand-text-dim">
                Last sync {formatTimestamp(lastUpdated)}
              </p>
              <p className="mt-1 text-[11px] font-mono font-bold uppercase tracking-wide text-brand-text-dim">
                Showing {signals.length}/{totalSignalCount} signals
              </p>
            </div>
          </div>

          {error ? (
            <div className="mt-5 flex flex-col gap-4 rounded-2xl border border-brand-rose/20 bg-brand-rose/5 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 text-brand-rose" />
                <p className="text-sm leading-relaxed text-brand-text">
                  {error}
                </p>
              </div>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-2 rounded-xl border border-brand-rose/30 px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest text-brand-rose transition-colors hover:border-brand-rose/60 hover:bg-brand-rose/10"
              >
                <RefreshCcw className="h-3.5 w-3.5" />
                Retry sync
              </button>
            </div>
          ) : null}
        </motion.section>

        <SearchPanel
          searchTerm={searchTerm}
          onSearch={onSearch}
          disabled={loading && totalSignalCount === 0}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 content-start items-start">
        <Heartbeat />

        {loading ? (
          Array.from({ length: 6 }).map((_, index) => (
            <SignalCardSkeleton key={`signal-skeleton-${index}`} index={index} />
          ))
        ) : null}

        {!loading && !isEmptyUniverse && !isEmptySearch ? (
          <AnimatePresence mode="popLayout">
            {signals.map((signal, index) => (
              <SignalCard
                key={signal.symbol}
                signal={signal}
                index={index}
              />
            ))}
          </AnimatePresence>
        ) : null}

        {isEmptyUniverse ? (
          <SignalGridStatus
            icon={<Inbox className="h-6 w-6" />}
            title="No live signals returned"
            message="The backend responded successfully but the signal universe is empty right now. This usually means the screener has not populated the database yet."
            actionLabel="Retry sync"
            onAction={onRetry}
          />
        ) : null}

        {isEmptySearch ? (
          <SignalGridStatus
            icon={<Search className="h-6 w-6" />}
            title={`No matches for "${searchTerm.trim()}"`}
            message="Try a ticker, a broader company fragment, or a sector keyword to widen the sweep."
          />
        ) : null}

        {!loading && totalSignalCount > 0 && hasSearch ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="brutalist-card p-5 border-dashed border-brand-border/70"
          >
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-brand-text-dim">
              Active Filter
            </p>
            <div className="mt-4 flex items-center justify-between gap-3">
              <div>
                <p className="font-display text-xl font-black tracking-tight">
                  {searchTerm.trim()}
                </p>
                <p className="mt-1 text-xs text-brand-text-dim">
                  Search is applied against symbol, name, and sector.
                </p>
              </div>
              <button
                type="button"
                onClick={() => onSearch('')}
                className="rounded-xl border border-white/10 px-3 py-2 text-[10px] font-mono font-bold uppercase tracking-widest text-brand-text-dim transition-colors hover:border-brand-accent/40 hover:text-brand-accent"
              >
                Clear
              </button>
            </div>
          </motion.div>
        ) : null}
      </div>
    </main>
  )
}
