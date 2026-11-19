import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { changePassword, updateProfile } from '@/api/auth'
import { fetchStats } from '@/api/stats'
import { ME_QUERY_KEY } from '@/features/auth/useAuth'
import type { User } from '@/types/api'

/** Save (or clear) the display name. The reply replaces the cached account, so the header updates at once. */
export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: updateProfile,
    onSuccess: (user) => queryClient.setQueryData<User | null>(ME_QUERY_KEY, user),
  })
}

/** Change the password. The browser keeps its session: the reply carries a fresh cookie. */
export function useChangePassword() {
  return useMutation({ mutationFn: changePassword })
}

export const STATS_QUERY_KEY = ['stats'] as const

/** The signed-in user's job statistics. Re-read each time the Settings page opens. */
export function useStats() {
  return useQuery({ queryKey: STATS_QUERY_KEY, queryFn: ({ signal }) => fetchStats(signal) })
}
