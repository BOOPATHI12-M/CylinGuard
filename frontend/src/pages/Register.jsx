/**
 * Create an account.
 *
 * The 72-byte password ceiling is bcrypt's, and the backend rejects anything longer
 * rather than letting it be silently truncated. The hint says so in plain language so a
 * user with a long passphrase is not left guessing at a 422.
 */

import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Loader2, ShieldCheck } from 'lucide-react'

import { useAuth } from '../context/AuthContext'

export function Register() {
  const { register, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()

  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && isAuthenticated) return <Navigate to="/dashboard" replace />

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value })

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await register(form.name, form.email, form.password)
      navigate('/dashboard', { replace: true })
    } catch (failure) {
      setError(failure)
    } finally {
      setSubmitting(false)
    }
  }

  const fields = [
    { id: 'name', label: 'Name', type: 'text', autoComplete: 'name', placeholder: 'Your name' },
    {
      id: 'email',
      label: 'Email',
      type: 'email',
      autoComplete: 'email',
      placeholder: 'you@example.com',
    },
    {
      id: 'password',
      label: 'Password',
      type: 'password',
      autoComplete: 'new-password',
      placeholder: '••••••••',
      hint: 'At least 8 characters, and at most 72 bytes — the limit bcrypt can hash without truncating.',
    },
  ]

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
          <h1 className="mt-3 text-xl font-semibold text-ink">Create your account</h1>
        </div>

        <form onSubmit={handleSubmit} className="glass space-y-4 p-5" noValidate>
          {error ? (
            <p role="alert" className="rounded-xl2 border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
              {error.message}
            </p>
          ) : null}

          {fields.map((field) => (
            <div key={field.id}>
              <label htmlFor={field.id} className="label">
                {field.label}
              </label>
              <input
                id={field.id}
                name={field.id}
                type={field.type}
                autoComplete={field.autoComplete}
                required
                value={form[field.id]}
                onChange={update(field.id)}
                aria-invalid={Boolean(error?.fields?.[field.id])}
                aria-describedby={
                  [
                    error?.fields?.[field.id] ? `${field.id}-error` : null,
                    field.hint ? `${field.id}-hint` : null,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
                className="field"
                placeholder={field.placeholder}
              />
              {field.hint ? (
                <p id={`${field.id}-hint`} className="mt-1 text-[11px] leading-relaxed text-ink-faint">
                  {field.hint}
                </p>
              ) : null}
              {error?.fields?.[field.id] ? (
                <p id={`${field.id}-error`} className="mt-1 text-xs text-danger">
                  {error.fields[field.id]}
                </p>
              ) : null}
            </div>
          ))}

          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting ? (
              <>
                <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                Creating account…
              </>
            ) : (
              'Create account'
            )}
          </button>

          <p className="text-center text-xs text-ink-muted">
            Already registered?{' '}
            <Link to="/login" className="text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </main>
  )
}
