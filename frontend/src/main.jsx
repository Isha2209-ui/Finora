import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './auth.jsx'
import { FinoraProvider } from './store.jsx'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <FinoraProvider>
          <App />
        </FinoraProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
