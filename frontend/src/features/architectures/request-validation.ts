/**
 * Client-side copy of the backend's rule for a design request
 * (ArchitectureRequest in api/schemas.py): surrounding whitespace is
 * stripped, then the text must be 10-4000 characters.
 */
export const REQUEST_MIN_LENGTH = 10
export const REQUEST_MAX_LENGTH = 4000

/** Length as the backend counts it: trimmed, in code points (Python counts an emoji as 1, JavaScript as 2). */
export function requestLength(text: string): number {
  return Array.from(text.trim()).length
}

/** A message explaining what to fix, or undefined when the backend will accept the text. */
export function validateRequest(text: string): string | undefined {
  const length = requestLength(text)
  if (length === 0) return 'Describe the system you want to design.'
  if (length < REQUEST_MIN_LENGTH) {
    return `Add a little more detail: at least ${REQUEST_MIN_LENGTH} characters (currently ${length}).`
  }
  if (length > REQUEST_MAX_LENGTH) {
    return `Shorten the description to ${REQUEST_MAX_LENGTH.toLocaleString('en')} characters or fewer (currently ${length.toLocaleString('en')}).`
  }
  return undefined
}
