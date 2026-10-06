/**
 * One WebSocket per cylinder, shared by every component that wants it (spec §39).
 *
 * The rule this file exists to enforce: **no per-component sockets.** Five panels on
 * the dashboard all want live state. If each opened its own connection the browser
 * would hold five sockets, the backend would broadcast five copies of every frame, and
 * a reconnect storm would multiply by five. So subscribers are reference-counted
 * against a single socket, and the socket closes when the last one leaves.
 *
 * Reconnection is exponential backoff with jitter. A fixed retry interval across many
 * open tabs synchronises into a thundering herd the moment a backend restarts; the
 * jitter spreads them out.
 */

import { tokenStore } from './api'

const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30000
// 1000 is a normal close: the page is navigating away or we closed it deliberately,
// so it must not trigger a reconnect.
const NORMAL_CLOSURE = 1000
// 1008 is the policy violation the server sends for a bad token or a cylinder the
// user does not own. Retrying would hammer the server with credentials it has already
// rejected, so this is terminal.
const POLICY_VIOLATION = 1008

export const STATUS = {
  connecting: 'connecting',
  open: 'open',
  reconnecting: 'reconnecting',
  closed: 'closed',
  unauthorized: 'unauthorized',
}

function socketUrl(cylinderId) {
  const token = tokenStore.get() ?? ''
  if (import.meta.env.VITE_WS_URL) {
    return `${import.meta.env.VITE_WS_URL}/dashboard/${cylinderId}?token=${encodeURIComponent(token)}`
  }
  // Same origin as the page, so Vite's dev proxy and NGINX both route it without the
  // app knowing which one is in front.
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}/ws/dashboard/${cylinderId}?token=${encodeURIComponent(token)}`
}

/** One entry per cylinder id. */
const channels = new Map()

function channelFor(cylinderId) {
  let channel = channels.get(cylinderId)
  if (channel) return channel

  channel = {
    cylinderId,
    socket: null,
    subscribers: new Set(),
    statusListeners: new Set(),
    status: STATUS.closed,
    attempt: 0,
    retryTimer: null,
    lastFrame: null,
    closing: false,
  }
  channels.set(cylinderId, channel)
  return channel
}

function setStatus(channel, status) {
  if (channel.status === status) return
  channel.status = status
  channel.statusListeners.forEach((listener) => listener(status))
}

function scheduleReconnect(channel) {
  if (channel.closing || channel.subscribers.size === 0) return

  channel.attempt += 1
  const backoff = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** (channel.attempt - 1))
  // Up to 30% jitter so many tabs do not all retry on the same tick.
  const delay = backoff * (0.85 + Math.random() * 0.3)

  setStatus(channel, STATUS.reconnecting)
  channel.retryTimer = setTimeout(() => {
    channel.retryTimer = null
    open(channel)
  }, delay)
}

function open(channel) {
  if (channel.socket || channel.closing) return

  setStatus(channel, channel.attempt === 0 ? STATUS.connecting : STATUS.reconnecting)

  let socket
  try {
    socket = new WebSocket(socketUrl(channel.cylinderId))
  } catch {
    scheduleReconnect(channel)
    return
  }
  channel.socket = socket

  socket.onopen = () => {
    channel.attempt = 0
    setStatus(channel, STATUS.open)
  }

  socket.onmessage = (event) => {
    let frame
    try {
      frame = JSON.parse(event.data)
    } catch {
      return // a frame we cannot parse is dropped, not fatal
    }
    if (frame?.type === 'pong') return
    channel.lastFrame = frame
    channel.subscribers.forEach((subscriber) => subscriber(frame))
  }

  socket.onerror = () => {
    /* onclose always follows, and that is where reconnection is decided */
  }

  socket.onclose = (event) => {
    channel.socket = null

    if (event.code === POLICY_VIOLATION) {
      // Terminal: the token is bad or the cylinder is not ours. Retrying cannot help.
      setStatus(channel, STATUS.unauthorized)
      return
    }
    if (channel.closing || event.code === NORMAL_CLOSURE) {
      setStatus(channel, STATUS.closed)
      return
    }
    scheduleReconnect(channel)
  }
}

function teardown(channel) {
  channel.closing = true
  if (channel.retryTimer) {
    clearTimeout(channel.retryTimer)
    channel.retryTimer = null
  }
  if (channel.socket) {
    channel.socket.onclose = null
    channel.socket.close(NORMAL_CLOSURE, 'component unmounted')
    channel.socket = null
  }
  channels.delete(channel.cylinderId)
}

/**
 * Subscribe to a cylinder's frames. Returns an unsubscribe function.
 *
 * The first subscriber opens the socket; the last one to leave closes it.
 */
export function subscribe(cylinderId, onFrame, onStatus) {
  const channel = channelFor(cylinderId)
  channel.closing = false

  channel.subscribers.add(onFrame)
  if (onStatus) {
    channel.statusListeners.add(onStatus)
    onStatus(channel.status)
  }

  // A late subscriber gets the last frame straight away rather than waiting for the
  // next tick, so a panel mounted after the others is not briefly empty.
  if (channel.lastFrame) onFrame(channel.lastFrame)

  if (!channel.socket && !channel.retryTimer) open(channel)

  return () => {
    channel.subscribers.delete(onFrame)
    if (onStatus) channel.statusListeners.delete(onStatus)
    if (channel.subscribers.size === 0) teardown(channel)
  }
}

/** Keeps an idle connection from being reaped by an intermediate proxy. */
export function ping(cylinderId) {
  const channel = channels.get(cylinderId)
  if (channel?.socket?.readyState === WebSocket.OPEN) channel.socket.send('ping')
}

/** Drop everything - used on sign-out, so a new user never inherits a socket. */
export function closeAll() {
  for (const channel of [...channels.values()]) teardown(channel)
}

/** Test and debug helper: how many sockets this module is actually holding. */
export function openSocketCount() {
  let count = 0
  for (const channel of channels.values()) if (channel.socket) count += 1
  return count
}
