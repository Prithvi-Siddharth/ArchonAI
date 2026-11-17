/** Semantic tones shared by badges, status, progress and toasts. */
export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

/** Text/icon color for a tone. */
export const TONE_TEXT: Record<Tone, string> = {
  neutral: 'text-muted-foreground',
  info: 'text-info',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
}

/** Tinted background, border and text -- badges and inline notices. */
export const TONE_SOFT: Record<Tone, string> = {
  neutral: 'border-border bg-surface-muted text-muted-foreground',
  info: 'border-info/25 bg-info/10 text-info',
  success: 'border-success/25 bg-success/10 text-success',
  warning: 'border-warning/25 bg-warning/10 text-warning',
  danger: 'border-danger/25 bg-danger/10 text-danger',
}

/** Solid fill -- progress bars and indicator dots. */
export const TONE_FILL: Record<Tone, string> = {
  neutral: 'bg-muted-foreground',
  info: 'bg-info',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
}
