/**
 * Desktop (browser) notifications. Asking for permission only ever happens from a button click
 * on the Settings page; the app never prompts by itself.
 */
import { create } from 'zustand'

import { readStorage, writeStorage } from '@/utils/storage'

export const DESKTOP_PREF_STORAGE_KEY = 'archonai-desktop-notifications'

export type DesktopSupport = 'unsupported' | 'insecure' | 'ready'

/** Whether this browser, on this address, can show desktop notifications at all. */
export function desktopSupport(): DesktopSupport {
  if (typeof Notification === 'undefined') return 'unsupported'
  // Browsers only allow notifications on localhost and HTTPS.
  if (typeof window !== 'undefined' && window.isSecureContext === false) return 'insecure'
  return 'ready'
}

export const permission = (): NotificationPermission | 'unsupported' => (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission)

interface DesktopState {
  /** The user's choice in this browser. It only takes effect while the browser permission is "granted". */
  enabled: boolean
  setEnabled: (enabled: boolean) => void
}

export const useDesktopPref = create<DesktopState>()((set) => ({
  enabled: readStorage(DESKTOP_PREF_STORAGE_KEY) === 'on',
  setEnabled: (enabled) => {
    writeStorage(DESKTOP_PREF_STORAGE_KEY, enabled ? 'on' : 'off')
    set({ enabled })
  },
}))

/** True when a desktop notification would actually be shown right now. */
export const desktopActive = () => desktopSupport() === 'ready' && permission() === 'granted' && useDesktopPref.getState().enabled

/** The tab can't be seen: another tab is in front, the window is minimised, or another app has focus. */
export const tabIsAway = () => document.visibilityState !== 'visible' || !document.hasFocus()

/** Show one notification. Never throws (some browsers refuse to build one, e.g. on some phones). */
export function showDesktop(title: string, body: string, tag: string, onClick: () => void): void {
  try {
    const note = new Notification(title, { body, tag })
    note.onclick = () => {
      window.focus()
      onClick()
      note.close()
    }
  } catch {
    // The in-app toast still shows.
  }
}

/** Ask the browser for permission (call only from a click). Turns the preference on when granted. */
export async function enableDesktop(): Promise<NotificationPermission | 'unsupported'> {
  if (desktopSupport() !== 'ready') return 'unsupported'
  let result: NotificationPermission
  try {
    result = await Notification.requestPermission()
  } catch {
    return permission()
  }
  useDesktopPref.getState().setEnabled(result === 'granted')
  return result
}
