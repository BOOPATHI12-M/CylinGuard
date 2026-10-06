import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { ToastProvider } from './components/ToastNotification'
import { AuthProvider } from './context/AuthContext'
import './index.css'

// Provider order matters: AuthProvider signs the user out on a rejected token, and the
// toast viewport should already exist by then so the app can say why.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
)
