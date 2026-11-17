import { create } from 'zustand'

export type ToastTone = 'info' | 'success' | 'warning' | 'danger'

export interface ToastOptions {
  title: string
  description?: string
  tone?: ToastTone
  /** Milliseconds before auto-dismiss; 0 keeps it until closed. Default 5000. */
  duration?: number
}

export interface ToastItem {
  id: string
  title: string
  description?: string
  tone: ToastTone
  duration: number
}

const MAX_VISIBLE = 4
let nextId = 0

interface ToastState {
  toasts: ToastItem[]
  show: (options: ToastOptions) => string
  dismiss: (id: string) => void
}

export const useToastStore = create<ToastState>()((set) => ({
  toasts: [],
  show: ({ title, description, tone = 'info', duration = 5000 }) => {
    const id = `toast-${++nextId}`
    set((state) => ({ toasts: [...state.toasts, { id, title, description, tone, duration }].slice(-MAX_VISIBLE) }))
    return id
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
}))

/** Show a toast from anywhere (components, event handlers, future API callbacks). Returns its id. */
export function toast(options: ToastOptions): string {
  return useToastStore.getState().show(options)
}
