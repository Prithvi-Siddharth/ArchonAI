import { formatDuration, formatNumber } from '@/utils/format'

export const EMPTY = '—'

/** "3m 12s", or "—" when the event that carries it was not logged. */
export const duration = (ms: number | null | undefined) => (ms === null || ms === undefined ? EMPTY : formatDuration(ms))

/** Milliseconds under a second are shown as such: "850 ms". */
export function shortDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return EMPTY
  return ms < 1000 ? `${formatNumber(ms)} ms` : formatDuration(ms)
}

export const count = (value: number | null | undefined) => (value === null || value === undefined ? EMPTY : formatNumber(value))

/** "14:03:27" in the viewer's own time zone. */
export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}
