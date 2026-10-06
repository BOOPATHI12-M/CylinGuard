/**
 * Transient notifications, and the app's single ARIA live region (spec §59).
 *
 * One region at the root rather than a live region per component: several live regions
 * compete, and a screen reader may announce them in an order nobody chose. Everything
 * that needs announcing goes through `useToast`.
 *
 * Politeness is chosen by severity. A critical alert is `assertive`, which interrupts -
 * which is the point, because it may be a gas leak. Everything else is `polite` and
 * waits for a pause, so routine confirmations do not talk over the user.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, Siren, X } from 'lucide-react'

const ToastContext = createContext(null)

const DEFAULT_TIMEOUT_MS = 5000

const VARIANTS = {
  info: { icon: Info, className: 'border-hairline bg-surface-raised/95 text-ink' },
  success: { icon: CheckCircle2, className: 'border-safe/30 bg-surface-raised/95 text-safe' },
  warning: { icon: AlertTriangle, className: 'border-warn/30 bg-surface-raised/95 text-warn' },
  critical: { icon: Siren, className: 'border-danger/40 bg-surface-raised/95 text-danger' },
}

let nextId = 1

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback((message, { variant = 'info', timeout } = {}) => {
    const id = nextId++
    // A critical toast is not auto-dismissed: the user must acknowledge it, or it could
    // vanish while they are looking away from the screen.
    const ttl = timeout ?? (variant === 'critical' ? null : DEFAULT_TIMEOUT_MS)
    setToasts((current) => [...current, { id, message, variant, ttl }])
    return id
  }, [])

  const value = useMemo(
    () => ({
      push,
      dismiss,
      info: (message) => push(message, { variant: 'info' }),
      success: (message) => push(message, { variant: 'success' }),
      warning: (message) => push(message, { variant: 'warning' }),
      critical: (message) => push(message, { variant: 'critical' }),
    }),
    [push, dismiss],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

function ToastViewport({ toasts, onDismiss }) {
  const hasCritical = toasts.some((toast) => toast.variant === 'critical')

  return (
    <div
      // Not a landmark: it must not appear in the list of regions a screen-reader user
      // tabs through, because its contents are transient.
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
      aria-live={hasCritical ? 'assertive' : 'polite'}
      aria-atomic="false"
    >
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}

function Toast({ toast, onDismiss }) {
  const { icon: Icon, className } = VARIANTS[toast.variant] ?? VARIANTS.info

  useEffect(() => {
    if (!toast.ttl) return undefined
    const timer = setTimeout(() => onDismiss(toast.id), toast.ttl)
    return () => clearTimeout(timer)
  }, [toast, onDismiss])

  return (
    <div
      className={`pointer-events-auto flex animate-fade-in-up items-start gap-2.5 rounded-xl2 border px-3.5 py-3 text-sm shadow-glass backdrop-blur-xl ${className}`}
    >
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="flex-1 leading-relaxed">{toast.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="rounded p-0.5 text-ink-muted hover:text-ink"
        aria-label="Dismiss notification"
      >
        <X aria-hidden="true" className="h-4 w-4" />
      </button>
    </div>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside a ToastProvider')
  return context
}
