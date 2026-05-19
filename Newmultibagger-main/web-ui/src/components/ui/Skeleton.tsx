/**
 * Skeleton.tsx — Loading skeleton primitives for the Sovereign Research Terminal.
 * Provides layout-aware placeholder blocks with shimmer animation.
 */

import type { CSSProperties, ReactNode } from 'react'

/* ─── Base Skeleton Block ──────────────────────────────────────────── */

interface SkeletonProps {
  className?: string
  width?: string | number
  height?: string | number
  style?: CSSProperties
  rounded?: boolean
  children?: ReactNode
}

export function Skeleton({
  className = '',
  width,
  height,
  style,
  rounded = false,
  children,
}: SkeletonProps) {
  return (
    <div
      className={`skeleton-shimmer ${rounded ? 'rounded-full' : 'rounded'} ${className}`}
      style={{
        width: width ?? '100%',
        height: height ?? '1rem',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ─── Preset Skeletons for Common Patterns ─────────────────────────── */

/** Full-width text line skeleton */
export function SkeletonLine({ width = '100%', height = '0.75rem' }: { width?: string; height?: string }) {
  return <Skeleton width={width} height={height} />
}

/** Score card skeleton */
export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`p-4 bg-black/40 border border-white/5 rounded flex flex-col gap-3 ${className}`}>
      <Skeleton width="60%" height="0.625rem" />
      <Skeleton width="40%" height="1.75rem" />
    </div>
  )
}

/** Chart area skeleton */
export function SkeletonChart({ height = '20rem' }: { height?: string }) {
  return (
    <div className="brutalist-card p-6">
      <div className="flex items-center gap-2 mb-6">
        <Skeleton width="1.25rem" height="1.25rem" rounded />
        <Skeleton width="40%" height="0.875rem" />
      </div>
      <Skeleton width="100%" height={height} />
    </div>
  )
}

/** Grid of metric cards (e.g., 2x2 or 4-col) */
export function SkeletonMetricGrid({ cols = 4, count = 4 }: { cols?: number; count?: number }) {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-${cols} gap-4`}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

/** Stock detail page loading skeleton */
export function StockDetailSkeleton() {
  return (
    <div className="min-h-screen bg-brand-bg text-brand-text p-4 md:p-8 pb-32 animate-in fade-in">
      {/* Terminal Header Accent */}
      <div className="flex items-center justify-center py-4 mb-6">
        <div className="animate-pulse font-mono tracking-widest text-brand-accent uppercase font-bold text-sm">
          [ DECRYPTING TERMINAL FEED ]
        </div>
      </div>

      {/* Nav */}
      <div className="flex items-center gap-4 mb-8">
        <Skeleton width="10rem" height="2rem" />
        <div className="flex-1" />
        <Skeleton width="6rem" height="2.25rem" />
        <Skeleton width="5rem" height="2.25rem" />
      </div>

      {/* Header Card */}
      <div className="brutalist-card p-6 md:p-8 mb-8">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <Skeleton width="8rem" height="2.5rem" />
              <Skeleton width="3.5rem" height="1.5rem" />
            </div>
            <Skeleton width="14rem" height="1rem" />
            <Skeleton width="10rem" height="0.75rem" />
          </div>
          <div className="flex flex-col items-end gap-2">
            <Skeleton width="7rem" height="2rem" />
            <Skeleton width="4rem" height="1rem" />
          </div>
        </div>
        <div className="mt-8 pt-6 border-t border-brand-border">
          <SkeletonMetricGrid cols={4} count={4} />
        </div>
      </div>

      {/* Body Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        <div className="xl:col-span-2 space-y-8">
          <SkeletonChart />
          <SkeletonChart height="12rem" />
        </div>
        <div className="xl:col-span-1 space-y-6">
          <div className="brutalist-card p-6">
            <Skeleton width="60%" height="0.75rem" className="mb-4" />
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} width="100%" height="2.5rem" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Score report page loading skeleton */
export function ScoreReportSkeleton() {
  return (
    <div className="min-h-screen bg-brand-bg text-brand-text p-4 md:p-8 pb-32 animate-in fade-in">
      <div className="flex items-center justify-center py-4 mb-6">
        <div className="animate-pulse font-mono tracking-widest text-brand-accent uppercase font-bold text-sm">
          [ COMPUTING SCORE DISTRIBUTION ]
        </div>
      </div>
      <Skeleton width="8rem" height="1.5rem" className="mb-8" />
      <div className="brutalist-card p-6 md:p-8 mb-8">
        <Skeleton width="8rem" height="0.625rem" className="mb-2" />
        <Skeleton width="60%" height="1.75rem" className="mb-2" />
        <Skeleton width="40%" height="0.75rem" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        <div className="xl:col-span-2 space-y-8">
          <SkeletonChart height="12rem" />
          <SkeletonMetricGrid cols={5} count={10} />
        </div>
        <div className="xl:col-span-1">
          <div className="brutalist-card p-5">
            <Skeleton width="50%" height="0.75rem" className="mb-4" />
            <Skeleton width="60%" height="2rem" className="mb-4" />
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} width="100%" height="3rem" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Watchlist page loading skeleton */
export function WatchlistSkeleton() {
  return (
    <div className="min-h-screen bg-brand-bg text-brand-text p-4 md:p-8 pb-32 animate-in fade-in">
      <div className="flex items-center justify-center py-4 mb-6">
        <div className="animate-pulse font-mono tracking-widest text-brand-accent uppercase font-bold text-sm">
          [ LOADING WATCHLIST ]
        </div>
      </div>
      <Skeleton width="8rem" height="1.5rem" className="mb-8" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="brutalist-card p-5">
            <div className="flex items-center justify-between mb-3">
              <Skeleton width="5rem" height="1.5rem" />
              <Skeleton width="2rem" height="1.5rem" />
            </div>
            <Skeleton width="70%" height="0.75rem" className="mb-4" />
            <div className="flex items-center gap-4">
              <Skeleton width="4rem" height="1.25rem" />
              <Skeleton width="3rem" height="1rem" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
