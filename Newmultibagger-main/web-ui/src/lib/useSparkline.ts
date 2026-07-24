/**
 * useSparkline
 *
 * Fetches recent price history for a single symbol, but only once the
 * calling element actually scrolls into view — the screener grid can
 * render 50-100 cards at once, and firing api.getHistory() for all of
 * them on mount would turn one page load into a hundred requests.
 *
 * Also caches per-symbol at module scope, so re-mounting a card (e.g.
 * clearing a search filter re-renders the grid) doesn't re-fetch.
 *
 * Usage
 * -----
 *   const cardRef = useRef<HTMLDivElement>(null)
 *   const { points, status } = useSparkline(signal.symbol, cardRef)
 */

import { useEffect, useRef, useState, type RefObject } from 'react'
import { api } from './api'
import type { HistoryPoint } from './contracts'

export type SparklineStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface UseSparklineResult {
  points: number[]
  status: SparklineStatus
}

const CACHE = new Map<string, number[]>()
const MAX_POINTS = 20

export function useSparkline(
  symbol: string,
  containerRef: RefObject<Element>,
): UseSparklineResult {
  const [points, setPoints] = useState<number[]>(() => CACHE.get(symbol) ?? [])
  const [status, setStatus] = useState<SparklineStatus>(CACHE.has(symbol) ? 'ready' : 'idle')
  const requested = useRef(false)

  useEffect(() => {
    if (CACHE.has(symbol)) return
    const el = containerRef.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      // No viewport-gating available — fail closed rather than crash;
      // the sparkline simply won't populate in this environment.
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (requested.current) return
        if (entries.some((entry) => entry.isIntersecting)) {
          requested.current = true
          observer.disconnect()
          setStatus('loading')

          api
            .getHistory(symbol)
            .then((history: HistoryPoint[]) => {
              const prices = history.slice(-MAX_POINTS).map((point) => point.price)
              CACHE.set(symbol, prices)
              setPoints(prices)
              setStatus('ready')
            })
            .catch(() => {
              // Sparkline is decorative — fail silently rather than
              // surfacing an error state on every card that lacks history.
              setStatus('error')
            })
        }
      },
      { rootMargin: '200px' },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [symbol, containerRef])

  return { points, status }
}
