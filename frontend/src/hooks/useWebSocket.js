/**
 * The only way a component reads live state.
 *
 * Every panel calls this hook; the module underneath reference-counts them onto one
 * socket per cylinder. A component that opened its own `new WebSocket` would break
 * that guarantee, which is why nothing else imports `services/websocket` directly
 * except the sign-out path.
 */

import { useEffect, useRef, useState } from 'react'

import { STATUS, ping, subscribe } from '../services/websocket'

const PING_INTERVAL_MS = 25000

export function useWebSocket(cylinderId) {
  const [frame, setFrame] = useState(null)
  const [status, setStatus] = useState(STATUS.closed)
  // Kept in a ref as well so the ping timer can read it without re-subscribing.
  const latest = useRef(null)

  useEffect(() => {
    if (!cylinderId) return undefined

    const unsubscribe = subscribe(
      cylinderId,
      (next) => {
        latest.current = next
        setFrame(next)
      },
      setStatus,
    )

    const keepalive = setInterval(() => ping(cylinderId), PING_INTERVAL_MS)

    return () => {
      clearInterval(keepalive)
      unsubscribe()
    }
  }, [cylinderId])

  return {
    frame,
    status,
    isLive: status === STATUS.open,
    // Surfaced separately because it is terminal - no amount of waiting fixes a
    // rejected token, so the UI should say so rather than show a spinner forever.
    isUnauthorized: status === STATUS.unauthorized,
  }
}

export { STATUS }
