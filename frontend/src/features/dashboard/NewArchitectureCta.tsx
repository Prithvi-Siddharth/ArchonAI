import { ArrowRight, SquarePlus } from 'lucide-react'
import { Link } from 'react-router'

import { buttonVariants } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { cn } from '@/utils/cn'

const STEPS = ['Describe your workload', 'Agents design and review it', 'Get the report and cost estimate']

export function NewArchitectureCta() {
  return (
    <Card className="flex flex-col p-5">
      <span className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
        <SquarePlus className="size-4" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-sm font-semibold">Design a new architecture</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Describe your requirements in plain language. ArchonAI&apos;s agents plan, design, review and cost an AWS
        architecture for them.
      </p>

      <ol className="mt-5 space-y-2.5 text-sm">
        {STEPS.map((step, index) => (
          <li key={step} className="flex items-center gap-3">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[11px] text-muted-foreground">
              {index + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>

      {/* mt-auto keeps the button at the bottom when the card stretches to the table's height. */}
      <div className="mt-auto pt-6">
        <Link to="/architectures/new" className={cn(buttonVariants(), 'w-full')}>
          New Architecture
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
    </Card>
  )
}
