// Referenced by vite.config.js as the vitest setupFiles entry.
import '@testing-library/jest-dom/vitest'

// jsdom has no WebSocket. The websocket module is tested against this stand-in, which
// records what was constructed and lets a test drive open/message/close by hand.
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.CONNECTING
    this.sent = []
    this.onopen = null
    this.onmessage = null
    this.onerror = null
    this.onclose = null
    MockWebSocket.instances.push(this)
  }

  send(data) {
    this.sent.push(data)
  }

  close(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code, reason })
  }

  // --- test helpers ---
  acceptConnection() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.({})
  }

  emit(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  dropConnection(code = 1006) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code, reason: 'abnormal' })
  }
}

globalThis.WebSocket = MockWebSocket
globalThis.MockWebSocket = MockWebSocket

beforeEach(() => {
  MockWebSocket.instances = []
  localStorage.clear()
})
