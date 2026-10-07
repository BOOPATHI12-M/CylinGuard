/**
 * The single HTTP client.
 *
 * One Axios instance for the whole app (spec §39). No component calls `fetch` or
 * builds its own client, so the base URL, the auth header and error shaping exist in
 * exactly one place.
 *
 * The base URL defaults to a *relative* `/api`, which is what makes the same build
 * work in dev and in production: Vite proxies `/api` to 127.0.0.1:8000 locally, and
 * NGINX proxies it to `backend:8000` in the container. `VITE_API_URL` overrides it for
 * the case where the API is on another origin.
 */

import axios from 'axios'

const TOKEN_KEY = 'cylinguard.token'

/**
 * The token lives in localStorage, which is readable by any script on the origin -
 * so this is only safe while the app ships no third-party scripts and no
 * user-rendered HTML. The alternative, an httpOnly cookie, needs CSRF protection and
 * a same-site deployment the compose stack does not yet have. Revisit if either
 * changes.
 *
 * Every access is wrapped: Safari in private mode throws on localStorage rather than
 * returning null.
 */
export const tokenStore = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* a session that cannot persist still works until reload */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* nothing to do */
    }
  },
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** Listeners notified when the server rejects our token, so the app can log out. */
const unauthorizedListeners = new Set()
export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

/**
 * Turn any failure into one predictable shape: `{ status, message, fields }`.
 *
 * Without this every component would have to know that FastAPI puts a string in
 * `detail` for an HTTPException but an array of field errors there for a 422, and that
 * a network failure has no response at all.
 */
export function normalizeError(error) {
  if (error.response) {
    const { status, data } = error.response
    const detail = data?.detail

    if (Array.isArray(detail)) {
      const fields = {}
      for (const item of detail) {
        // loc is ["body", "field"]; the last element is the field name.
        const key = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : 'form'
        fields[key] = item.msg
      }
      const first = detail[0]?.msg ?? 'Please check the highlighted fields.'
      return { status, message: first, fields }
    }

    return {
      status,
      message: typeof detail === 'string' ? detail : fallbackMessage(status),
      fields: {},
    }
  }

  if (error.code === 'ECONNABORTED') {
    return { status: 0, message: 'The request timed out. Is the backend running?', fields: {} }
  }
  return {
    status: 0,
    message: 'Cannot reach the server. Check that the backend is running.',
    fields: {},
  }
}

function fallbackMessage(status) {
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return 'You do not have access to that.'
  if (status === 404) return 'Not found.'
  if (status === 409) return 'No data has been recorded for this cylinder yet.'
  if (status === 503) return 'The service is temporarily unavailable.'
  if (status >= 500) return 'Something went wrong on the server.'
  return 'Request failed.'
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const normalized = normalizeError(error)
    // A 401 on the login route is a wrong password, not an expired session - letting
    // it log the user out would clear a token they never had.
    const isLoginAttempt = error.config?.url?.includes('/auth/login')
    if (normalized.status === 401 && !isLoginAttempt) {
      tokenStore.clear()
      unauthorizedListeners.forEach((listener) => listener())
    }
    return Promise.reject(normalized)
  },
)

/* --- endpoints, named so no component hand-writes a path ------------------ */

export const auth = {
  login: (email, password) => api.post('/auth/login', { email, password }).then((r) => r.data),
  register: (name, email, password) =>
    api.post('/auth/register', { name, email, password }).then((r) => r.data),
  me: () => api.get('/auth/me').then((r) => r.data),
}

export const monitoring = {
  dashboard: (id) => api.get(`/dashboard/${id}`).then((r) => r.data),
  consumption: (id, days = 30) =>
    api.get(`/consumption/${id}`, { params: { days } }).then((r) => r.data),
  prediction: (id) => api.get(`/prediction/${id}`).then((r) => r.data),
  safety: (id, limit = 20) => api.get(`/safety/${id}`, { params: { limit } }).then((r) => r.data),
  history: (id, { page = 1, size = 50, since, until, gasExceeded, deviceStatus } = {}) =>
    api
      .get(`/history/${id}`, {
        // Axios omits undefined params, so an unset filter is simply absent rather than
        // sent as the string "undefined".
        params: {
          page,
          size,
          since,
          until,
          gas_exceeded: gasExceeded,
          device_status: deviceStatus,
        },
      })
      .then((r) => r.data),
  alerts: (id, { unreadOnly = false, severity, limit = 50 } = {}) =>
    api
      .get(`/alerts/${id}`, { params: { unread_only: unreadOnly, severity, limit } })
      .then((r) => r.data),
  markAlertRead: (alertId) => api.post(`/alerts/${alertId}/read`).then((r) => r.data),
  settings: (id) => api.get(`/settings/${id}`).then((r) => r.data),
  updateSettings: (id, patch) => api.put(`/settings/${id}`, patch).then((r) => r.data),
}

export const demo = {
  state: (id) => api.get(`/demo/${id}`).then((r) => r.data),
  toggle: (id, enabled) => api.post(`/demo/${id}/toggle`, { enabled }).then((r) => r.data),
  scenario: (id, scenario) => api.post(`/demo/${id}/scenario`, { scenario }).then((r) => r.data),
}

/**
 * Liveness. Deliberately *not* on the `api` instance: /health sits outside /api, and
 * routing it through the baseURL resolved to the SPA shell and returned index.html
 * with a 200 - a health check that can never fail is worse than none.
 */
export const health = () => axios.get('/health').then((r) => r.data)
