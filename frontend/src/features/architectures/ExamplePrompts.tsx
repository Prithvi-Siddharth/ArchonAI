import { CircleAlert, RotateCw } from 'lucide-react'
import { useId } from 'react'

import { Button, Skeleton, Tooltip } from '@/components/ui'
import type { ExamplePrompt } from '@/types/api'

import { useExamplePrompts } from './useArchitectureApi'

interface ExamplePromptsProps {
  onSelect: (example: ExamplePrompt) => void
  disabled?: boolean
}

/** "Start from an example": the backend's example prompts. Optional -- the form works without them. */
export function ExamplePrompts({ onSelect, disabled = false }: ExamplePromptsProps) {
  const labelId = useId()
  const examples = useExamplePrompts()

  if (examples.isSuccess && examples.data.length === 0) return null

  return (
    <div role="group" aria-labelledby={labelId} aria-busy={examples.isPending || undefined} className="space-y-2.5">
      <p id={labelId} className="text-label">
        Start from an example
      </p>

      {examples.isPending ? (
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-control-sm w-32" />
          ))}
          <span className="sr-only">Loading examples</span>
        </div>
      ) : examples.isError ? (
        <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <CircleAlert className="size-4 shrink-0 text-danger" aria-hidden="true" />
            Couldn&apos;t load examples. You can still describe your system below.
          </span>
          <Button variant="ghost" size="sm" onClick={() => examples.refetch()} loading={examples.isFetching}>
            {!examples.isFetching && <RotateCw className="size-3.5" aria-hidden="true" />}
            Retry
          </Button>
        </div>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {examples.data.map((example) => (
            <li key={example.label}>
              <Tooltip content={example.prompt} side="bottom">
                <Button variant="outline" size="sm" disabled={disabled} onClick={() => onSelect(example)}>
                  {example.label}
                </Button>
              </Tooltip>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
