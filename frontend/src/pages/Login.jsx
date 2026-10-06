/**
 * Sign in.
 *
 * Errors are rendered from `normalizeError`'s shape, and field errors land on their own
 * inputs via `aria-describedby` rather than only in a banner at the top - a screen
 * reader user filling a form should hear what is wrong with the field they are in.
 */

import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Loader2, ShieldCheck } from 'lucide-react'

import { useAuth } from '../context/AuthContext'

export function Login() {
  const { signIn, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && isAuthenticated) {
    // Send them where they were heading before the redirect to /login.
    return <Navigate to={location.state?.from ?? '/dashboard'} replace />
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await signIn(email, password)
      navigate(location.state?.from ?? '/dashboard', { replace: true })
    } catch (failure) {
      setError(failure)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="grid min-h-full place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <span
            aria-hidden="true"
            className="grid h-12 w-12 place-items-center rounded-xl2 border border-accent/30 bg-accent-soft text-accent"
          >
            <ShieldCheck className="h-6 w-6" />
          </span>
          <h1 className="mt-3 text-xl font-semibold text-ink">CylinGuard</h1>
          <p className="mt-1 text-sm text-ink-muted">Sign in to monitor your cylinder.</p>
        </div>

        <form onSubmit={handleSubmit} className="glass space-y-4 p-5" noValidate>
          {error ? (
            <p role="alert" className="rounded-xl2 border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
              {error.message}
            </p>
          ) : null}

          <div>
            <label htmlFor="email" className="label">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(error?.fields?.email)}
              aria-describedby={error?.fields?.email ? 'email-error' : undefined}
              className="field"
              placeholder="you@example.com"
            />
            {error?.fields?.email ? (
              <p id="email-error" className="mt-1 text-xs text-danger">
                {error.fields.email}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="password" className="label">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(error?.fields?.password)}
              aria-describedby={error?.fields?.password ? 'password-error' : undefined}
              className="field"
              placeholder="••••••••"
            />
            {error?.fields?.password ? (
              <p id="password-error" className="mt-1 text-xs text-danger">
                {error.fields.password}
              </p>
            ) : null}
          </div>

          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting ? (
              <>
                <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                Signing in…
              </>
            ) : (
              'Sign in'
            )}
          </button>

          <p className="text-center text-xs text-ink-muted">
            No account?{' '}
            <Link to="/register" className="text-accent hover:underline">
              Create one
            </Link>
          </p>
        </form>
      </div>
    </main>
  )
}
