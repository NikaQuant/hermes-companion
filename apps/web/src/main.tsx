import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { AuthProvider } from './context/AuthContext'
import './styles.css'

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => undefined))
}

async function listenForNativeLinks() {
  try {
    const { App: CapacitorApp } = await import('@capacitor/app')
    await CapacitorApp.addListener('appUrlOpen', event => {
      const url = new URL(event.url)
      window.history.replaceState({}, '', `${url.pathname}${url.search}`)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
  } catch {
    // Browser/PWA: Capacitor runtime is intentionally absent.
  }
}
void listenForNativeLinks()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
)
