import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchMe, login, logout, register } from '@/api/auth'
import type { User } from '@/types/api'

/** The signed-in account. `null` means signed out (the API answered 401). */
export const ME_QUERY_KEY = ['auth', 'me'] as const

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => fetchMe(signal),
    // Checked again on the next page load after 5 minutes; a 401 from any other request
    // signs the user out sooner (see app/providers.tsx).
    staleTime: 5 * 60_000,
  })
}

/** Sign in. On success the account is cached, which takes the user into the app. */
export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: login,
    onSuccess: (user) => queryClient.setQueryData<User | null>(ME_QUERY_KEY, user),
  })
}

/** Create an account; the backend signs in to it straight away. */
export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: register,
    onSuccess: (user) => queryClient.setQueryData<User | null>(ME_QUERY_KEY, user),
  })
}

/**
 * Sign out. Everything cached for the previous account (jobs, results) is dropped, so the
 * next person to use this browser never sees it.
 */
export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData<User | null>(ME_QUERY_KEY, null)
    },
  })
}
