import { ExternalLink, Mail, MapPin, Phone } from 'lucide-react'
import type { ReactNode } from 'react'

import portrait from '@/assets/creator.jpg'
import { buttonVariants, Card, CardContent, PageHeader } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import { CREATOR, type CreatorInfo } from './creator-info'

function ContactRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 text-muted-foreground" aria-hidden="true">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-meta text-muted-foreground">{label}</p>
        <div className="break-words">{children}</div>
      </div>
    </li>
  )
}

const linkClass = 'font-medium text-primary hover:underline'

function ProfileLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={buttonVariants({ variant: 'outline' })}>
      {children}
      <ExternalLink className="size-3.5" aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  )
}

export function CreatorCard({ info = CREATOR }: { info?: CreatorInfo }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-6 py-6 sm:flex-row sm:items-start sm:gap-8">
        <img
          src={portrait}
          alt={`Portrait of ${info.name}`}
          width={512}
          height={640}
          className="aspect-[4/5] w-40 shrink-0 rounded-lg border border-border object-cover object-top sm:w-48"
        />
        <div className="min-w-0 flex-1 space-y-5">
          <div className="space-y-1">
            <p className="text-overline text-muted-foreground uppercase">Creator of ArchonAI</p>
            <h2 className="text-page-title">{info.name}</h2>
            <p className="text-muted-foreground">{info.role}</p>
          </div>

          <ul aria-label="Contact details" className="space-y-3">
            <ContactRow icon={<Mail className="size-4" />} label="Email">
              <a href={`mailto:${info.email}`} className={linkClass}>
                {info.email}
              </a>
            </ContactRow>
            <ContactRow icon={<Phone className="size-4" />} label="Phone">
              <a href={`tel:${info.phone.replace(/[^\d+]/g, '')}`} className={linkClass}>
                {info.phone}
              </a>
            </ContactRow>
            <ContactRow icon={<MapPin className="size-4" />} label="Location">
              {info.location}
            </ContactRow>
          </ul>

          {(info.github || info.linkedin) && (
            <div className="flex flex-wrap gap-3">
              {info.github && <ProfileLink href={info.github}>GitHub</ProfileLink>}
              {info.linkedin && <ProfileLink href={info.linkedin}>LinkedIn</ProfileLink>}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/** Who built ArchonAI, and how to reach them. */
export function CreatorPage() {
  useDocumentTitle('Creator')
  return (
    <div className="space-y-6">
      <PageHeader title="Creator" description="The person who built ArchonAI." />
      <div className="max-w-3xl">
        <CreatorCard />
      </div>
    </div>
  )
}
