import { Search, X } from 'lucide-react'

import { Input, type InputProps } from './Input'

interface SearchInputProps extends Omit<InputProps, 'value' | 'onChange' | 'type' | 'leadingIcon' | 'trailing'> {
  value: string
  onValueChange: (value: string) => void
}

/** Search box with a clear button; Escape clears it first (a second Escape reaches any enclosing dialog). */
export function SearchInput({ value, onValueChange, placeholder = 'Search…', onKeyDown, ...props }: SearchInputProps) {
  return (
    <Input
      type="search"
      leadingIcon={Search}
      placeholder={placeholder}
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && value) {
          event.preventDefault()
          onValueChange('')
        }
        onKeyDown?.(event)
      }}
      className="[&::-webkit-search-cancel-button]:appearance-none"
      trailing={
        value ? (
          <button
            type="button"
            onClick={() => onValueChange('')}
            aria-label="Clear search"
            className="flex size-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-surface-muted hover:text-foreground"
          >
            <X className="size-3.5" aria-hidden="true" />
          </button>
        ) : null
      }
      {...props}
    />
  )
}
