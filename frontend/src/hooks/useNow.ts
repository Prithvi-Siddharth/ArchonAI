import { useEffect, useState } from 'react'

/** The current time (ms), updated every `intervalMs`; pass null to stop ticking. */
export function useNow(intervalMs: number | null): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (intervalMs === null) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])

  return now
}
