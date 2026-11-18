/**
 * Possible (name-based, unconfirmed) matches between a free-text data-flow
 * label and the services list. The backend does not link the two, so callers
 * must present these as possible matches only.
 */
import type { AWSService } from '@/types/api'

const VENDOR_WORDS = new Set(['amazon', 'aws'])

/** Split "CloudFront + WAF", "DynamoDB / ElastiCache", "ECS (Fargate)" into comparable parts. */
function parts(text: string): Array<{ key: string; initials: string }> {
  const pieces = text
    .replace(/[()]/g, ' + ')
    .split(/\s*(?:\+|\/|,|&|\band\b)\s*/i)
    .map((piece) => piece.trim())
    .filter(Boolean)
  return pieces
    .map((piece) => {
      const words = piece.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w && !VENDOR_WORDS.has(w))
      return { key: words.join(''), initials: words.map((w) => w[0]).join('') }
    })
    .filter((part) => part.key.length >= 2)
}

function partsMatch(a: { key: string; initials: string }, b: { key: string; initials: string }): boolean {
  if (a.key === b.key) return true
  const [shorter, longer] = a.key.length <= b.key.length ? [a.key, b.key] : [b.key, a.key]
  if (shorter.length >= 3 && longer.startsWith(shorter)) return true // "aurora" ~ "aurorapostgresql"
  // Acronyms: "ALB" ~ "Application Load Balancer".
  return (a.key.length >= 2 && a.key === b.initials && b.initials.length >= 2) || (b.key === a.initials && a.initials.length >= 2)
}

/** Services whose name resembles the label, in services-list order. */
export function possibleServiceMatches(label: string, services: AWSService[]): AWSService[] {
  const labelParts = parts(label)
  if (labelParts.length === 0) return []
  return services.filter((service) => {
    const serviceParts = parts(service.name)
    return labelParts.some((lp) => serviceParts.some((sp) => partsMatch(lp, sp)))
  })
}
