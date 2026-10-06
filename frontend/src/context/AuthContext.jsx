/**
 * Who is signed in, and the one place the token is set or cleared.
 *
 * On a cold load the stored token is verified against `/auth/me` before the app
 * decides the user is signed in. Trusting the token's presence alone would render an
 * authenticated shell that then fails every request - the user would see a dashboard
 * frame full of errors instead of a login form.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { auth as authApi, onUnauthorized, tokenStore } from '../services/api'
import { closeAll } from '../services/websocket'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // `loading` starts true so a protected route waits for verification instead of
  // bouncing the user to /login for a moment on every refresh.
  const [loading, setLoading] = useState(true)

  const signOut = useCallback(() => {
    tokenStore.clear()
    // Sockets carry the old token in their URL, so they must not outlive the session.
    closeAll()
    setUser(null)
  }, [])

  useEffect(() => {
    let cancelled = false

    if (!tokenStore.get()) {
      setLoading(false)
      return () => {
        cancelled = true
      }
    }

    authApi
      .me()
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        // Expired or forged: clear it rather than leaving a token that fails silently.
        if (!cancelled) signOut()
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [signOut])

  // The Axios interceptor reports a rejected token from anywhere in the app, including
  // a background poll, so the session ends in one place rather than per call site.
  useEffect(() => onUnauthorized(signOut), [signOut])

  const signIn = useCallback(async (email, password) => {
    const data = await authApi.login(email, password)
    tokenStore.set(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const register = useCallback(async (name, email, password) => {
    const data = await authApi.register(name, email, password)
    tokenStore.set(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const value = useMemo(
    () => ({ user, loading, signIn, register, signOut, isAuthenticated: Boolean(user) }),
    [user, loading, signIn, register, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}
