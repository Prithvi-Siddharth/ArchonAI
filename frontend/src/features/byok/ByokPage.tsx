import { PageHeader } from '@/components/ui/PageHeader'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import { LLMKeyCard } from './LLMKeyCard'

/** Bring your own key: run your jobs on your own LLM provider account. */
export function ByokPage() {
  useDocumentTitle('Bring Your Own Key')
  return (
    <div className="space-y-6">
      <PageHeader title="Bring Your Own Key" description="Use your own LLM provider account for your architecture jobs." />
      <div className="max-w-2xl">
        <LLMKeyCard />
      </div>
    </div>
  )
}
