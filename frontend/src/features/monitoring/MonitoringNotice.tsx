import { CircleAlert, Info, RotateCw, ScrollText } from 'lucide-react'

import { Button, Card, EmptyState } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import type { JobMonitoring } from '@/types/api'
import { cn } from '@/utils/cn'

const TITLES: Record<string, string> = {
  empty: 'No log lines found for this job',
  disabled: 'CloudWatch logging is switched off',
  no_credentials: 'No AWS credentials on the server',
  forbidden: 'The server can’t read CloudWatch Logs',
  throttled: 'CloudWatch is busy',
  unreachable: 'CloudWatch couldn’t be reached',
}

/** Why there is nothing to show yet: not an error page, just an honest reason (and a retry where it could help). */
export function MonitoringNotice({ data, onRetry, retrying }: { data: JobMonitoring; onRetry: () => void; retrying: boolean }) {
  const transient = data.state === 'throttled' || data.state === 'unreachable' || data.state === 'empty'
  const warning = data.state === 'forbidden' || data.state === 'throttled' || data.state === 'unreachable' || data.state === 'no_credentials'
  return (
    <Card>
      <EmptyState
        icon={data.state === 'empty' ? ScrollText : warning ? CircleAlert : Info}
        title={TITLES[data.state] ?? 'Monitoring isn’t available'}
        description={data.message ?? 'Please try again later.'}
        action={
          transient ? (
            <Button variant="outline" onClick={onRetry} loading={retrying}>
              {!retrying && <RotateCw className="size-4" aria-hidden="true" />}
              Check again
            </Button>
          ) : undefined
        }
      />
      {data.may_still_arrive && data.state === 'empty' && (
        <p className={cn('mx-5 mb-5 rounded-md border px-3 py-2 text-center', TONE_SOFT.info)}>
          This job is running or just finished, so lines may still arrive. This page checks again every 10 seconds.
        </p>
      )}
    </Card>
  )
}
