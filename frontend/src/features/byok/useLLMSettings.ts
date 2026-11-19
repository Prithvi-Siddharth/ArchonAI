import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { deleteLLMSettings, fetchLLMSettings, saveLLMSettings } from '@/api/llmSettings'
import type { LLMSettings } from '@/types/api'

export const LLM_SETTINGS_QUERY_KEY = ['settings', 'llm'] as const

/** The signed-in user's saved provider settings. */
export function useLLMSettings() {
  return useQuery({ queryKey: LLM_SETTINGS_QUERY_KEY, queryFn: ({ signal }) => fetchLLMSettings(signal) })
}

/** Save a key or model. The reply (which never holds the key) replaces the cached settings. */
export function useSaveLLMSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: saveLLMSettings,
    onSuccess: (settings) => queryClient.setQueryData<LLMSettings>(LLM_SETTINGS_QUERY_KEY, settings),
  })
}

/** Remove the saved key; jobs go back to the server's provider. */
export function useDeleteLLMSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteLLMSettings,
    onSuccess: () =>
      queryClient.setQueryData<LLMSettings>(LLM_SETTINGS_QUERY_KEY, (current) =>
        current && { ...current, configured: false, provider: null, model: null, key_hint: null, updated_at: null },
      ),
  })
}
