/**
 * The single-socket and reconnect guarantees.
 *
 * These are the frontend's equivalent of the backend's rule tests: each one encodes a
 * decision that would otherwise live only in a comment, and each would be easy to break
 * by accident while adding a panel.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { closeAll, openSocketCount, ping, subscribe, STATUS } from './websocket'
import { tokenStore } from './api'

const CYLINDER = 1

function latestSocket() {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

beforeEach(() => {
  tokenStore.set('test-token')
  vi.useFakeTimers()
})

afterEach(() => {
  closeAll()
  vi.useRealTimers()
})

describe('one connection per cylinder', () => {
  it('opens a single socket no matter how many subscribers there are', () => {
    const unsubscribers = [
      subscribe(CYLINDER, vi.fn()),
      subscribe(CYLINDER, vi.fn()),
      subscribe(CYLINDER, vi.fn()),
      subscribe(CYLINDER, vi.fn()),
      subscribe(CYLINDER, vi.fn()),
    ]

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(openSocketCount()).toBe(1)

    unsubscribers.forEach((unsubscribe) => unsubscribe())
  })

  it('fans one frame out to every subscriber', () => {
    const first = vi.fn()
    const second = vi.fn()
    const stop = [subscribe(CYLINDER, first), subscribe(CYLINDER, second)]

    latestSocket().acceptConnection()
    latestSocket().emit({ lpg: { remaining_kg: 8.308 } })

    expect(first).toHaveBeenCalledWith({ lpg: { remaining_kg: 8.308 } })
    expect(second).toHaveBeenCalledWith({ lpg: { remaining_kg: 8.308 } })

    stop.forEach((fn) => fn())
  })

  it('gives a late subscriber the last frame immediately', () => {
    const early = subscribe(CYLINDER, vi.fn())
    latestSocket().acceptConnection()
    latestSocket().emit({ lpg: { remaining_kg: 8.1 } })

    // A panel mounted after the others should not sit empty until the next tick.
    const late = vi.fn()
    const stopLate = subscribe(CYLINDER, late)
    expect(late).toHaveBeenCalledWith({ lpg: { remaining_kg: 8.1 } })

    early()
    stopLate()
  })

  it('keeps separate cylinders on separate sockets', () => {
    const one = vi.fn()
    const two = vi.fn()
    const stop = [subscribe(1, one), subscribe(2, two)]

    expect(MockWebSocket.instances).toHaveLength(2)
    MockWebSocket.instances[0].acceptConnection()
    MockWebSocket.instances[0].emit({ cylinder: 1 })

    expect(one).toHaveBeenCalledWith({ cylinder: 1 })
    expect(two).not.toHaveBeenCalled()

    stop.forEach((fn) => fn())
  })

  it('closes the socket when the last subscriber leaves', () => {
    const stopA = subscribe(CYLINDER, vi.fn())
    const stopB = subscribe(CYLINDER, vi.fn())
    latestSocket().acceptConnection()

    stopA()
    expect(openSocketCount()).toBe(1) // B is still watching

    stopB()
    expect(openSocketCount()).toBe(0)
  })

  it('does not notify a component after it unsubscribes', () => {
    const listener = vi.fn()
    const stop = subscribe(CYLINDER, listener)
    const socket = latestSocket()
    socket.acceptConnection()

    stop()
    socket.emit({ lpg: { remaining_kg: 1 } })
    expect(listener).not.toHaveBeenCalled()
  })
})

describe('reconnection', () => {
  it('retries after an abnormal close, with a growing delay', () => {
    const stop = subscribe(CYLINDER, vi.fn())
    latestSocket().acceptConnection()
    expect(MockWebSocket.instances).toHaveLength(1)

    latestSocket().dropConnection(1006)

    // Nothing immediately: an instant retry against a backend that is still restarting
    // is a tight loop.
    expect(MockWebSocket.instances).toHaveLength(1)

    vi.advanceTimersByTime(1500) // first delay is ~1s plus jitter
    expect(MockWebSocket.instances).toHaveLength(2)

    latestSocket().dropConnection(1006)
    vi.advanceTimersByTime(1500) // second delay is ~2s, so this is too early
    expect(MockWebSocket.instances).toHaveLength(2)

    vi.advanceTimersByTime(2000)
    expect(MockWebSocket.instances).toHaveLength(3)

    stop()
  })

  it('reports reconnecting, then open again', () => {
    const statuses = []
    const stop = subscribe(CYLINDER, vi.fn(), (status) => statuses.push(status))

    latestSocket().acceptConnection()
    expect(statuses).toContain(STATUS.open)

    latestSocket().dropConnection(1006)
    vi.advanceTimersByTime(1500)
    expect(statuses).toContain(STATUS.reconnecting)

    latestSocket().acceptConnection()
    expect(statuses[statuses.length - 1]).toBe(STATUS.open)

    stop()
  })

  it('resets the backoff after a successful reconnect', () => {
    const stop = subscribe(CYLINDER, vi.fn())
    latestSocket().acceptConnection()

    latestSocket().dropConnection(1006)
    vi.advanceTimersByTime(1500)
    latestSocket().acceptConnection() // recovered, so the next failure starts at ~1s

    latestSocket().dropConnection(1006)
    vi.advanceTimersByTime(1500)
    expect(MockWebSocket.instances).toHaveLength(3)

    stop()
  })

  it('does not retry after a policy violation', () => {
    // 1008 is a rejected token or someone else's cylinder. Retrying would hammer the
    // server with credentials it has already refused.
    const statuses = []
    const stop = subscribe(CYLINDER, vi.fn(), (status) => statuses.push(status))

    latestSocket().dropConnection(1008)
    vi.advanceTimersByTime(60000)

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(statuses[statuses.length - 1]).toBe(STATUS.unauthorized)

    stop()
  })

  it('does not retry after a normal close', () => {
    const stop = subscribe(CYLINDER, vi.fn())
    latestSocket().acceptConnection()

    latestSocket().close(1000, 'going away')
    vi.advanceTimersByTime(60000)
    expect(MockWebSocket.instances).toHaveLength(1)

    stop()
  })

  it('stops retrying once nobody is subscribed', () => {
    const stop = subscribe(CYLINDER, vi.fn())
    latestSocket().acceptConnection()
    latestSocket().dropConnection(1006)

    stop() // the component unmounted while the retry was pending
    vi.advanceTimersByTime(60000)
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})

describe('plumbing', () => {
  it('carries the token in the URL, since browsers cannot set socket headers', () => {
    const stop = subscribe(CYLINDER, vi.fn())
    expect(latestSocket().url).toContain('token=test-token')
    expect(latestSocket().url).toContain(`/ws/dashboard/${CYLINDER}`)
    stop()
  })

  it('ignores a malformed frame instead of throwing', () => {
    const listener = vi.fn()
    const stop = subscribe(CYLINDER, listener)
    const socket = latestSocket()
    socket.acceptConnection()

    expect(() => socket.onmessage({ data: 'not json' })).not.toThrow()
    expect(listener).not.toHaveBeenCalled()
    stop()
  })

  it('does not pass pong replies off as dashboard frames', () => {
    const listener = vi.fn()
    const stop = subscribe(CYLINDER, listener)
    latestSocket().acceptConnection()

    latestSocket().emit({ type: 'pong' })
    expect(listener).not.toHaveBeenCalled()
    stop()
  })

  it('pings only an open socket', () => {
    const stop = subscribe(CYLINDER, vi.fn())
    ping(CYLINDER)
    expect(latestSocket().sent).toEqual([]) // still connecting

    latestSocket().acceptConnection()
    ping(CYLINDER)
    expect(latestSocket().sent).toEqual(['ping'])
    stop()
  })

  it('closeAll drops every socket, so a new user inherits none', () => {
    subscribe(1, vi.fn())
    subscribe(2, vi.fn())
    expect(openSocketCount()).toBe(2)

    closeAll()
    expect(openSocketCount()).toBe(0)
  })
})
