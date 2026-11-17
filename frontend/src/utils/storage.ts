/**
 * localStorage access that never throws: storage can be blocked (private
 * mode, disabled site data), and UI preferences must not break the app.
 */
export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Not persisted; the preference still applies for this visit.
  }
}
