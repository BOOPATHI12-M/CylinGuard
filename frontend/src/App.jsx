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
import { Alerts } from './pages/Alerts'
import { Consumption } from './pages/Consumption'
import { Dashboard } from './pages/Dashboard'
import { History } from './pages/History'
import { Login } from './pages/Login'
import { Prediction } from './pages/Prediction'
import { Register } from './pages/Register'
import { Safety } from './pages/Safety'
import { Settings } from './pages/Settings'

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
        <Route path="consumption" element={<Consumption />} />
        <Route path="prediction" element={<Prediction />} />
        <Route path="safety" element={<Safety />} />
        <Route path="history" element={<History />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="settings" element={<Settings />} />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
