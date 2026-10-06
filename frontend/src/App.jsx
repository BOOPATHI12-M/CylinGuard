/**
 * Routes, and the gate in front of them.
 *
 * `ProtectedRoute` waits for `AuthContext` to finish verifying the stored token before
 * deciding anything. Redirecting while `loading` is still true would bounce every user
 * to /login for a frame on each refresh, and would lose the page they asked for.
 */

import { Loader2 } from 'lucide-react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { useAuth } from './context/AuthContext'
import { AppLayout } from './layouts/AppLayout'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { Placeholder } from './pages/Placeholder'
import { Register } from './pages/Register'

function FullPageSpinner({ label }) {
  return (
    <div className="grid min-h-full place-items-center" role="status" aria-label={label}>
      <Loader2 aria-hidden="true" className="h-6 w-6 animate-spin text-accent" />
      <span className="sr-only">{label}</span>
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) return <FullPageSpinner label="Checking your session" />
  if (!isAuthenticated) {
    // Remember where they were going, so sign-in returns them there.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}

const FEATURE_PAGES = [
  { path: 'consumption', title: 'Consumption', note: 'Today, 7-day, 30-day and monthly totals with the 7D / 30D / 3M chart tabs.' },
  { path: 'prediction', title: 'Prediction', note: 'Radial confidence, days remaining and the depletion date, badged ESTIMATE until the model is trained in phase 6.' },
  { path: 'safety', title: 'Safety', note: 'The large state indicator, gas value against its threshold, commanded buzzer and relay state, and the event history.' },
  { path: 'history', title: 'History', note: 'The readings table with search, date and status filters over server-side pagination.' },
  { path: 'alerts', title: 'Alerts', note: 'Severity-grouped alerts with mark-as-read.' },
  { path: 'settings', title: 'Settings', note: 'The ten per-cylinder tunables. Nothing secret is reachable from here.' },
]

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard" element={<Dashboard />} />
        {FEATURE_PAGES.map(({ path, title, note }) => (
          <Route key={path} path={path} element={<Placeholder title={title} note={note} />} />
        ))}
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
