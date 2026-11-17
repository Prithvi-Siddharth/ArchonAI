import { LoaderCircle } from 'lucide-react'
import type { ComponentProps } from 'react'

import { cn } from '@/utils/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive'
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon-sm' | 'icon'

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary-hover',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary-hover',
  outline: 'border border-border-strong bg-transparent text-foreground hover:bg-surface-muted',
  ghost: 'text-muted-foreground hover:bg-surface-muted hover:text-foreground',
  destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive-hover',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-control-sm gap-1.5 px-3',
  md: 'h-control-md gap-2 px-4',
  lg: 'h-control-lg gap-2 px-5',
  'icon-sm': 'size-control-sm',
  icon: 'size-control-md',
}

/** Button classes, also used to style router <Link>s as buttons. */
export function buttonVariants({ variant = 'primary', size = 'md' }: { variant?: ButtonVariant; size?: ButtonSize } = {}) {
  return cn(
    'inline-flex shrink-0 items-center justify-center rounded-md text-label whitespace-nowrap transition-colors',
    'disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0',
    VARIANTS[variant],
    SIZES[size],
  )
}

export interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Shows a spinner, disables the button and sets aria-busy. */
  loading?: boolean
}

export function Button({
  variant,
  size,
  loading = false,
  disabled,
  className,
  type = 'button',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading && <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  )
}
