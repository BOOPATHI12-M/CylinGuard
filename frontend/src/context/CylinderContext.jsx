/**
 * Which cylinder the app is looking at.
 *
 * Replaces the `ACTIVE_CYLINDER_ID = 1` constant the phase 4 shell carried. That
 * constant meant a newly registered user, who owns no cylinder 1, got a 404 with no
 * explanation - and no account could ever have a second cylinder.
 *
 * The choice is remembered in localStorage so a refresh does not snap back to the first
 * cylinder, but it is always validated against what the API returned: a remembered id
 * for a cylinder that has since been deleted, or that belongs to the user who was signed
 * in before, must not survive.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { api } from '../services/api'
import { useAuth } from './AuthContext'

const STORAGE_KEY = 'cylinguard.cylinderId'
const CylinderContext = createContext(null)

function remembered() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? Number(raw) : null
  } catch {
    return null
  }
}

function remember(id) {
  try {
    localStorage.setItem(STORAGE_KEY, String(id))
  } catch {
    /* a choice that cannot persist still works for this session */
  }
}

export function CylinderProvider({ children }) {
  const { isAuthenticated } = useAuth()
  const [cylinders, setCylinders] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get('/cylinders')
      setCylinders(data)

      setActiveId((current) => {
        const ids = data.map((row) => row.id)
        // Keep the current selection if it is still ours, else fall back to the
        // remembered one, else the first cylinder, else nothing.
        if (current && ids.includes(current)) return current
        const saved = remembered()
        if (saved && ids.includes(saved)) return saved
        return data[0]?.id ?? null
      })
    } catch (failure) {
      setError(failure)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isAuthenticated) {
      setCylinders([])
      setActiveId(null)
      setLoading(false)
      return
    }
    load()
  }, [isAuthenticated, load])

  const select = useCallback((id) => {
    setActiveId(id)
    remember(id)
  }, [])

  const value = useMemo(() => {
    const active = cylinders.find((row) => row.id === activeId) ?? null
    return {
      cylinders,
      activeId,
      active,
      loading,
      error,
      select,
      refresh: load,
      // True when the account genuinely owns nothing - distinct from still loading,
      // and the reason the UI can explain itself instead of showing an empty frame.
      isEmpty: !loading && !error && cylinders.length === 0,
    }
  }, [cylinders, activeId, loading, error, select, load])

  return <CylinderContext.Provider value={value}>{children}</CylinderContext.Provider>
}

export function useCylinders() {
  const context = useContext(CylinderContext)
  if (!context) throw new Error('useCylinders must be used inside a CylinderProvider')
  return context
}
