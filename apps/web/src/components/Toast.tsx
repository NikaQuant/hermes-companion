import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

interface ToastItem { id: number; kind: 'success' | 'error' | 'info'; message: string }
interface ToastContextValue { push: (message: string, kind?: ToastItem['kind']) => void }
const ToastContext = createContext<ToastContextValue | null>(null)
let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const remove = useCallback((id: number) => setItems(current => current.filter(item => item.id !== id)), [])
  const push = useCallback((message: string, kind: ToastItem['kind'] = 'info') => {
    const id = nextId++
    setItems(current => [...current, { id, kind, message }])
    window.setTimeout(() => remove(id), 5000)
  }, [remove])
  const value = useMemo(() => ({ push }), [push])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {items.map(item => {
          const Icon = item.kind === 'success' ? CheckCircle2 : item.kind === 'error' ? AlertCircle : Info
          return <div key={item.id} className={`toast toast-${item.kind}`}><Icon size={17} /><span>{item.message}</span><button onClick={() => remove(item.id)}><X size={15} /></button></div>
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used inside ToastProvider')
  return value
}
