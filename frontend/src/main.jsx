import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './auth.jsx'
import { FinoraProvider } from './store.jsx'
import { OverlayProvider } from './components/ui.jsx'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <OverlayProvider>
        <AuthProvider>
          <FinoraProvider>
            <App />
          </FinoraProvider>
        </AuthProvider>
      </OverlayProvider>
    </BrowserRouter>
  </StrictMode>,
)
