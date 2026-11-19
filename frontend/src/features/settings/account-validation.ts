/** Client-side checks for the Settings forms; the backend (api/schemas.py) enforces the same rules. */

export const DISPLAY_NAME_MIN = 2
export const DISPLAY_NAME_MAX = 60

/** Characters as the backend counts them (code points, so an emoji counts once). */
const length = (value: string) => Array.from(value).length

/** Whitespace trimmed and runs of it collapsed, as the backend stores it. Empty means "no display name". */
export const normaliseDisplayName = (value: string) => value.split(/\s+/).filter(Boolean).join(' ')

export function validateDisplayName(value: string): string | undefined {
  const name = normaliseDisplayName(value)
  if (!name) return undefined
  if (length(name) < DISPLAY_NAME_MIN || length(name) > DISPLAY_NAME_MAX) {
    return `The display name must be ${DISPLAY_NAME_MIN} to ${DISPLAY_NAME_MAX} characters.`
  }
  return undefined
}
