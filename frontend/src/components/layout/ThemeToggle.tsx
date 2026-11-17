import { Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { useUIStore } from '@/stores/ui.store'

export function ThemeToggle() {
  const theme = useUIStore((state) => state.theme)
  const toggleTheme = useUIStore((state) => state.toggleTheme)
  const label = `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`

  return (
    <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={label} title={label}>
      {theme === 'dark' ? <Sun className="size-4" aria-hidden="true" /> : <Moon className="size-4" aria-hidden="true" />}
    </Button>
  )
}
