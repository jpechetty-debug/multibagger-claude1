import { useState, useCallback, useSyncExternalStore } from 'react'

const STORAGE_KEY = 'sovereign-watchlist'

let currentWatchlist: string[] = []

try {
  const raw = localStorage.getItem(STORAGE_KEY)
  currentWatchlist = raw ? JSON.parse(raw) : []
} catch {
  currentWatchlist = []
}

const listeners = new Set<() => void>()

function subscribe(callback: () => void) {
  listeners.add(callback)
  return () => listeners.delete(callback)
}

function getSnapshot() {
  return currentWatchlist
}

function notify() {
  const raw = localStorage.getItem(STORAGE_KEY)
  try {
    const next = raw ? JSON.parse(raw) : []
    // Only update reference if content changed
    if (JSON.stringify(next) !== JSON.stringify(currentWatchlist)) {
      currentWatchlist = next
      listeners.forEach(cb => cb())
    }
  } catch {
    // Ignore errors
  }
}

// Global listeners to sync the singleton
window.addEventListener('storage', (e) => {
  if (e.key === STORAGE_KEY) notify()
})
window.addEventListener('watchlist-update', () => notify())

function notifyChange() {
  window.dispatchEvent(new Event('watchlist-update'))
}

export function useWatchlist() {
  const symbols = useSyncExternalStore(subscribe, getSnapshot)

  const addToWatchlist = useCallback((symbol: string) => {
    const raw = localStorage.getItem(STORAGE_KEY)
    const current = raw ? JSON.parse(raw) : []
    if (!current.includes(symbol)) {
      const updated = [...current, symbol]
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
      notifyChange()
    }
  }, [])

  const removeFromWatchlist = useCallback((symbol: string) => {
    const raw = localStorage.getItem(STORAGE_KEY)
    const current = raw ? JSON.parse(raw) : []
    const updated = current.filter((s: string) => s !== symbol)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    notifyChange()
  }, [])


  const toggleWatchlist = useCallback((symbol: string) => {
    const current = getSnapshot()
    if (current.includes(symbol)) {
      removeFromWatchlist(symbol)
    } else {
      addToWatchlist(symbol)
    }
  }, [addToWatchlist, removeFromWatchlist])

  const isInWatchlist = useCallback((symbol: string): boolean => {
    return symbols.includes(symbol)
  }, [symbols])

  const clearWatchlist = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([]))
    notifyChange()
  }, [])

  return {
    watchlist: symbols,
    addToWatchlist,
    removeFromWatchlist,
    toggleWatchlist,
    isInWatchlist,
    clearWatchlist,
    count: symbols.length,
  }
}
