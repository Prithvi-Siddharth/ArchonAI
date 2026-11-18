/**
 * `relative_cost_breakdown` values are free text. In every stored result they
 * are "low", "medium" or "high" -- an ordinal ranking, not an amount or a
 * percentage. This only recognises that scale; anything else is shown as text.
 */
export type CostLevel = 1 | 2 | 3

const LEVELS: Record<string, CostLevel> = { low: 1, medium: 2, high: 3 }

/** 1-3 for "low" / "medium" / "high" (any case, surrounding spaces ignored); null for anything else. */
export function costLevel(value: string): CostLevel | null {
  return LEVELS[value.trim().toLowerCase()] ?? null
}
