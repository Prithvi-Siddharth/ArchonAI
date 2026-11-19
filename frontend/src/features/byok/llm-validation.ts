/** Client-side checks for the provider form; the backend (api/schemas.py) enforces the same rules. */

export const API_KEY_MIN = 8
export const API_KEY_MAX = 512
export const MODEL_MAX = 100
const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]*$/

/** `required` is true for a first save, or when the provider changed; otherwise an empty key means "keep the saved one". */
export function validateApiKey(value: string, required: boolean, providerLabel: string): string | undefined {
  const key = value.trim()
  if (!key) return required ? `Enter your ${providerLabel} API key.` : undefined
  if (key.length < API_KEY_MIN || key.length > API_KEY_MAX) return `The API key must be ${API_KEY_MIN} to ${API_KEY_MAX} characters.`
  if (/[\s\u0000-\u001f\u007f]/.test(key)) return "The API key can't contain spaces or line breaks."
  return undefined
}

export function validateModel(value: string): string | undefined {
  const model = value.trim()
  if (!model) return undefined
  if (model.length > MODEL_MAX || !MODEL_PATTERN.test(model)) {
    return `The model name can only use letters, digits and . _ : / - (up to ${MODEL_MAX} characters).`
  }
  return undefined
}
