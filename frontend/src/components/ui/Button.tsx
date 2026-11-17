import type { ComponentProps } from 'react'

import { cn } from '@/utils/cn'

type ButtonVariant = 'primary' | 'secondary' | 'ghost'
type ButtonSize = 'sm' | 'md' | 'icon'

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary-hover',
  secondary: 'border border-border bg-surface text-foreground hover:bg-surface-muted',
  ghost: 'text-muted-foreground hover:bg-surface-muted hover:text-foreground',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3',
  md: 'h-9 px-4',
  icon: 'size-9',
}

/** Button classes, also used to style router <Link>s as buttons. */
export function buttonVariants({ variant = 'primary', size = 'md' }: { variant?: ButtonVariant; size?: ButtonSize } = {}) {
  return cn(
    'inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors',
    'disabled:pointer-events-none disabled:opacity-50',
    VARIANTS[variant],
    SIZES[size],
  )
}

interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant
  size?: ButtonSize
}

export function Button({ variant, size, className, type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
