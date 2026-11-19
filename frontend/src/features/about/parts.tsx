import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Card, CardContent } from '@/components/ui'

/** A titled block of prose inside a tab. */
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-card-title">{title}</h3>
      <div className="space-y-2 leading-6 text-muted-foreground">{children}</div>
    </section>
  )
}

export function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 marker:text-muted-foreground">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  )
}

export function InlineLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-primary hover:underline">
      {children}
    </Link>
  )
}

/** A tab's content: one card of sections with dividers between them. */
export function Prose({ children }: { children: ReactNode }) {
  return (
    <Card>
      <CardContent className="space-y-6 py-6 [&>section+section]:border-t [&>section+section]:border-border [&>section+section]:pt-6">
        {children}
      </CardContent>
    </Card>
  )
}
