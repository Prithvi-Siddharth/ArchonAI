import type { ComponentProps } from 'react'

import { cn } from '@/utils/cn'

import { TONE_SOFT, type Tone } from './tones'

interface BadgeProps extends ComponentProps<'span'> {
  tone?: Tone
}

export function Badge({ tone = 'neutral', className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-meta font-medium whitespace-nowrap',
        TONE_SOFT[tone],
        className,
      )}
      {...props}
    />
  )
}
