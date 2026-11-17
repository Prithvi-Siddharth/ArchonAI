import { Moon, Sun } from 'lucide-react'

import { Button, Tooltip } from '@/components/ui'
import { useUIStore } from '@/stores/ui.store'

export function ThemeToggle() {
  const theme = useUIStore((state) => state.theme)
  const toggleTheme = useUIStore((state) => state.toggleTheme)
  const label = `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`

  return (
    <Tooltip content={label} side="bottom" describeTrigger={false}>
      <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={label}>
        {theme === 'dark' ? <Sun className="size-4" aria-hidden="true" /> : <Moon className="size-4" aria-hidden="true" />}
      </Button>
    </Tooltip>
  )
}
