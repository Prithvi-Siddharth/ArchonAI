import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchExamplePrompts, submitArchitectureJob } from '@/api/architectures'
import { toast } from '@/stores/toast.store'
import { shortId } from '@/utils/format'

import { invalidateJobHistory } from './history/useJobHistory'

/** The example prompts (GET /examples). They come from a static file on the backend, so load them once per session. */
export function useExamplePrompts() {
  return useQuery({
    queryKey: ['architectures', 'examples'],
    queryFn: ({ signal }) => fetchExamplePrompts(signal),
    staleTime: Infinity,
  })
}

/**
 * Submit a design request (POST /jobs). Never retried automatically (see
 * submitArchitectureJob). Refreshing the history and the toast happen here rather
 * than in the form, so both still happen if the user leaves the page while the
 * request is in flight. The job itself is saved to the user's account by the API.
 */
export function useSubmitArchitectureJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: submitArchitectureJob,
    onSuccess: (job) => {
      void invalidateJobHistory(queryClient)
      toast({ tone: 'success', title: 'Architecture job queued', description: `Job ${shortId(job.job_id)}` })
    },
  })
}
