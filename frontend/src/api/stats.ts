/** The signed-in user's own job statistics (backend: api/routes/stats.py). */
import type { Stats } from '@/types/api'

import { apiRequest } from './client'

export const STATS_PATH = '/api/v1/stats'

export function fetchStats(signal?: AbortSignal): Promise<Stats> {
  return apiRequest<Stats>(STATS_PATH, { signal })
}
