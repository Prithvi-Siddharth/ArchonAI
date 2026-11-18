import { useState } from 'react'

import { PageHeader } from '@/components/ui'

import { ArchitectureRequestForm, type SubmittedJob } from './ArchitectureRequestForm'
import { RequestGuide } from './RequestGuide'
import { SubmissionSuccess } from './SubmissionSuccess'

export function NewArchitecturePage() {
  const [submitted, setSubmitted] = useState<SubmittedJob | null>(null)
  // After "Submit another", focus goes to the fresh text box (not on the first visit).
  const [returning, setReturning] = useState(false)

  return (
    <div className="space-y-6">
      <PageHeader
        title="New Architecture"
        description="Describe the system you need. ArchonAI's agents turn it into a reviewed AWS architecture with a cost estimate."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        {/* Wrapper keeps the card at its own height instead of stretching to the guide's. */}
        <div className="min-w-0">
          {submitted ? (
            <SubmissionSuccess
              submitted={submitted}
              onNewRequest={() => {
                setReturning(true)
                setSubmitted(null)
              }}
            />
          ) : (
            <ArchitectureRequestForm onSubmitted={setSubmitted} autoFocus={returning} />
          )}
        </div>
        <RequestGuide />
      </div>
    </div>
  )
}
