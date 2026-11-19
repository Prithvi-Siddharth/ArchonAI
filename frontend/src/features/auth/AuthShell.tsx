import { ArrowLeft, CircleAlert, Eye, EyeOff } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { Brand } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { Card, Input, type InputProps } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import { cn } from '@/utils/cn'

/** Full-screen frame for the sign-in and registration pages (outside the app layout). */
export function AuthShell({ title, description, children, footer }: { title: string; description: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="flex h-header shrink-0 items-center justify-between gap-3 px-4 sm:px-6">
        <Brand />
        <ThemeToggle />
      </header>
      <main className="flex flex-1 justify-center px-4 pt-6 pb-12 sm:items-center sm:pt-0">
        <div className="w-full max-w-sm space-y-4">
          <Link to="/welcome" className="inline-flex items-center gap-1.5 rounded-sm text-meta text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            Back to welcome
          </Link>
          <Card className="px-5 py-6 sm:px-6">
            <h1 className="text-page-title">{title}</h1>
            <p className="mt-1 text-muted-foreground">{description}</p>
            <div className="mt-6">{children}</div>
          </Card>
          <p className="text-center text-muted-foreground">{footer}</p>
        </div>
      </main>
    </div>
  )
}

/** A form-level error (e.g. wrong password, server unreachable), announced to screen readers. */
export function FormAlert({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className={cn('flex items-start gap-2 rounded-md border px-3 py-2.5', TONE_SOFT.danger)}>
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p className="min-w-0 break-words">{children}</p>
    </div>
  )
}

/** Password input with a show/hide toggle. Use inside <Field>. */
export function PasswordInput(props: Omit<InputProps, 'type' | 'trailing'>) {
  const [visible, setVisible] = useState(false)
  const Icon = visible ? EyeOff : Eye
  return (
    <Input
      {...props}
      type={visible ? 'text' : 'password'}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide password' : 'Show password'}
          aria-pressed={visible}
          className="flex size-7 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground"
        >
          <Icon className="size-4" aria-hidden="true" />
        </button>
      }
    />
  )
}
