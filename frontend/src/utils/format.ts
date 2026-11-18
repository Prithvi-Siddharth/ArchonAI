const numberFormat = new Intl.NumberFormat('en')
const relativeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const dateTimeFormat = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' })
const timeFormat = new Intl.DateTimeFormat('en', { timeStyle: 'short' })

const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

/** `part` as a whole-number percentage of `total` ("89%"); "0%" when total is 0. */
export function formatPercent(part: number, total: number): string {
  return total > 0 ? `${Math.round((part / total) * 100)}%` : '0%'
}

/** "5 minutes ago", "yesterday", ... */
export function formatRelativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) {
      return relativeFormat.format(Math.round(seconds / size), unit)
    }
  }
  return 'just now'
}

/** "Nov 17, 2026, 2:30 PM" */
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** The first 8 characters of a job UUID, as shown in the UI. */
export function shortId(id: string): string {
  return id.slice(0, 8)
}

/** "4:59 PM" */
export function formatTime(iso: string): string {
  return timeFormat.format(new Date(iso))
}

/** A length of time: "45s", "9m 05s", "1h 02m". Negative values (clock skew) count as 0. */
export function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m`
  if (minutes > 0) return `${minutes}m ${String(seconds).padStart(2, '0')}s`
  return `${seconds}s`
}
