import { useMutation, useQuery } from '@tanstack/react-query'

import { fetchExamplePrompts, submitArchitectureJob } from '@/api/architectures'
import { useSubmissionsStore } from '@/stores/submissions.store'
import { toast } from '@/stores/toast.store'
import { shortId } from '@/utils/format'

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
 * submitArchitectureJob). Recording the job and the toast happen here rather
 * than in the form, so both still happen if the user leaves the page while the
 * request is in flight.
 */
export function useSubmitArchitectureJob() {
  return useMutation({
    mutationFn: submitArchitectureJob,
    onSuccess: (job, userRequest) => {
      useSubmissionsStore.getState().record(job.job_id, userRequest)
      toast({ tone: 'success', title: 'Architecture job queued', description: `Job ${shortId(job.job_id)}` })
    },
  })
}
