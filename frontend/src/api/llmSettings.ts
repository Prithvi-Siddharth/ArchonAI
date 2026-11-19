/** Bring-your-own-key endpoints (backend: api/routes/llm_settings.py). The key is sent once and never read back. */
import type { LLMSettings, LLMSettingsUpdate } from '@/types/api'

import { apiRequest } from './client'

export const LLM_SETTINGS_PATH = '/api/v1/settings/llm'

/** GET -- the saved provider, model and key hint (never the key). */
export function fetchLLMSettings(signal?: AbortSignal): Promise<LLMSettings> {
  return apiRequest<LLMSettings>(LLM_SETTINGS_PATH, { signal })
}

/** PUT -- save a provider and key, or only change the model of the saved key. 422 for invalid input. */
export function saveLLMSettings(update: LLMSettingsUpdate): Promise<LLMSettings> {
  return apiRequest<LLMSettings>(LLM_SETTINGS_PATH, { method: 'PUT', body: update })
}

/** DELETE -- remove the saved key (204). Safe to repeat. */
export function deleteLLMSettings(): Promise<void> {
  return apiRequest<void>(LLM_SETTINGS_PATH, { method: 'DELETE' })
}
