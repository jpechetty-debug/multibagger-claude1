/**
 * useLivePrices
 *
 * Connects to /ws/prices and keeps the price map up-to-date.
 *
 * Auth flow
 * ---------
 * 1. Fetch a short-lived token from GET /api/ws-token (uses the same
 *    VITE_SOVEREIGN_API_KEY the REST client uses).
 * 2. Open ws[s]://…/ws/prices?token=<token>.
 * 3. On close/error, wait with exponential backoff (1 s → 2 → 4 → … → 60 s
 *    cap) then restart from step 1 so the token is always fresh.
 *
 * Exposed state
 * -------------
 *   prices   — Map<symbol, { price, changePct, updatedAt }>
 *   status   — 'connecting' | 'open' | 'closed' | 'error'
 *   latencyMs — round-trip echo latency (null until first pong)
 *
 * Usage
 * -----
 *   const { prices, status } = useLivePrices()
 *   const live = prices.get('INFY')   // { price, changePct, updatedAt }
 *
 * The hook is safe to mount multiple times — each instance manages its
 * own connection.  For a singleton, lift it to a React context.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export type WsStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

export interface LivePrice {
  price: number
  changePct: number
  updatedAt: number   // Date.now() timestamp
}

export interface UseLivePricesResult {
  /** symbol → latest price snapshot */
  prices: Map<string, LivePrice>
  /** current WebSocket lifecycle state */
  status: WsStatus
  /** round-trip latency in ms; null before first echo */
  latencyMs: number | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_KEY = import.meta.env.VITE_SOVEREIGN_API_KEY?.trim() ?? ''
const BASE_URL = ''   // same origin

const BACKOFF_INITIAL_MS  = 1_000
const BACKOFF_MAX_MS      = 60_000
const BACKOFF_MULTIPLIER  = 2
const PING_INTERVAL_MS    = 20_000   // send a ping every 20 s to detect dead connections

// ── Token fetch ───────────────────────────────────────────────────────────────

interface WsTokenResponse {
  token: string
  ttl_seconds: number
}

async function fetchWsToken(): Promise<string> {
  const res = await fetch(`${BASE_URL}/api/ws-token`, {
    headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
  })
  if (!res.ok) {
    throw new Error(`ws-token request failed: ${res.status}`)
  }
  const body: WsTokenResponse = await res.json()
  if (!body.token) throw new Error('ws-token response missing token field')
  return body.token
}

// ── WebSocket URL builder ─────────────────────────────────────────────────────

function buildWsUrl(token: string): string {
  const proto  = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host   = window.location.host
  return `${proto}://${host}/ws/prices?token=${encodeURIComponent(token)}`
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useLivePrices(): UseLivePricesResult {
  const [prices, setPrices]     = useState<Map<string, LivePrice>>(new Map())
  const [status, setStatus]     = useState<WsStatus>('idle')
  const [latencyMs, setLatency] = useState<number | null>(null)

  // Mutable refs so the effect cleanup can always reach the latest values
  // without re-registering the effect.
  const wsRef          = useRef<WebSocket | null>(null)
  const retryCount     = useRef(0)
  const retryTimer     = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer      = useRef<ReturnType<typeof setInterval> | null>(null)
  const pingTimestamp  = useRef<number | null>(null)
  const destroyed      = useRef(false)

  const clearTimers = useCallback(() => {
    if (retryTimer.current)  { clearTimeout(retryTimer.current);  retryTimer.current  = null }
    if (pingTimer.current)   { clearInterval(pingTimer.current);  pingTimer.current   = null }
  }, [])

  const closeSocket = useCallback(() => {
    const ws = wsRef.current
    if (!ws) return
    wsRef.current = null
    // Remove listeners before close so onclose doesn't trigger a reconnect
    // after the hook is unmounted.
    ws.onopen    = null
    ws.onmessage = null
    ws.onclose   = null
    ws.onerror   = null
    if (ws.readyState < WebSocket.CLOSING) ws.close(1000, 'hook unmounted')
  }, [])

  const connect = useCallback(async () => {
    if (destroyed.current) return

    setStatus('connecting')

    // ── Fetch a fresh token ───────────────────────────────────────────────────
    let token: string
    try {
      token = await fetchWsToken()
    } catch (err) {
      if (destroyed.current) return
      console.warn('[useLivePrices] token fetch failed:', err)
      setStatus('error')
      scheduleRetry()   // will be defined below via ref trick
      return
    }

    if (destroyed.current) return

    // ── Open the socket ───────────────────────────────────────────────────────
    let ws: WebSocket
    try {
      ws = new WebSocket(buildWsUrl(token))
    } catch (err) {
      console.warn('[useLivePrices] WebSocket construction failed:', err)
      setStatus('error')
      scheduleRetry()
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      if (destroyed.current) { ws.close(); return }
      setStatus('open')
      retryCount.current = 0   // reset backoff on successful connect

      // Start heartbeat ping
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          pingTimestamp.current = Date.now()
          ws.send(JSON.stringify({ type: 'ping' }))
        }
      }, PING_INTERVAL_MS)
    }

    ws.onmessage = (event: MessageEvent) => {
      if (destroyed.current) return

      let data: Record<string, unknown>
      try {
        data = JSON.parse(event.data as string)
      } catch {
        return
      }

      // Pong — measure latency
      if (data.type === 'pong' && pingTimestamp.current !== null) {
        setLatency(Date.now() - pingTimestamp.current)
        pingTimestamp.current = null
        return
      }

      // Price update — shape: { symbol: string, price: number, change_pct?: number }
      const symbol = typeof data.symbol === 'string' ? data.symbol : null
      const price  = typeof data.price  === 'number' ? data.price  : null
      if (!symbol || price === null) return

      const changePct = typeof data.change_pct === 'number' ? data.change_pct : 0

      setPrices(prev => {
        const next = new Map(prev)
        next.set(symbol, { price, changePct, updatedAt: Date.now() })
        return next
      })
    }

    ws.onclose = (event: CloseEvent) => {
      clearTimers()
      wsRef.current = null
      if (destroyed.current) return

      // 1000 = normal close (we initiated), 1001 = going away — don't retry.
      if (event.code === 1000 || event.code === 1001) {
        setStatus('closed')
        return
      }

      // 1008 = Policy Violation (auth failure) — log clearly, still retry
      // (token may have been transient; a fresh one will be fetched).
      if (event.code === 1008) {
        console.warn('[useLivePrices] ws closed 1008 (auth rejected); will retry with fresh token')
      }

      setStatus('closed')
      scheduleRetry()
    }

    ws.onerror = () => {
      // onerror is always followed by onclose — let onclose handle the retry.
      setStatus('error')
    }
  }, [clearTimers])   // eslint-disable-line react-hooks/exhaustive-deps

  // Needs to reference connect — use a ref to break the circular dep.
  const connectRef = useRef(connect)
  connectRef.current = connect

  const scheduleRetry = useCallback(() => {
    if (destroyed.current) return
    const delay = Math.min(
      BACKOFF_INITIAL_MS * Math.pow(BACKOFF_MULTIPLIER, retryCount.current),
      BACKOFF_MAX_MS,
    )
    retryCount.current += 1
    console.info(`[useLivePrices] reconnecting in ${Math.round(delay / 1000)}s (attempt ${retryCount.current})`)
    retryTimer.current = setTimeout(() => connectRef.current(), delay)
  }, [])

  // Boot the connection once on mount; tear down on unmount.
  useEffect(() => {
    destroyed.current = false
    void connectRef.current()

    return () => {
      destroyed.current = true
      clearTimers()
      closeSocket()
      setStatus('closed')
    }
  }, [clearTimers, closeSocket])

  return { prices, status, latencyMs }
}
