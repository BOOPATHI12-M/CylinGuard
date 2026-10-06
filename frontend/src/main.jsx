import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { ToastProvider } from './components/ToastNotification'
import { AuthProvider } from './context/AuthContext'
import { CylinderProvider } from './context/CylinderContext'
import './index.css'

// Provider order matters: AuthProvider signs the user out on a rejected token, and the
// toast viewport should already exist by then so the app can say why.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          {/* Inside AuthProvider: the cylinder list is per user and must reload when the
              signed-in user changes. */}
          <CylinderProvider>
            <App />
          </CylinderProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
)
