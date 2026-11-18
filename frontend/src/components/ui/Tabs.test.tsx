import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { Tabs } from './Tabs'

const ITEMS = [
  { id: 'one', label: 'One' },
  { id: 'two', label: 'Two' },
  { id: 'three', label: 'Three' },
]

function Harness({ initial = 'one' }: { initial?: string }) {
  const [value, setValue] = useState(initial)
  return (
    <Tabs label="Sections" items={ITEMS} value={value} onValueChange={setValue}>
      <p>Panel {value}</p>
    </Tabs>
  )
}

const tab = (name: string) => screen.getByRole('tab', { name })

afterEach(() => cleanup())

describe('Tabs', () => {
  it('exposes a labelled tablist, selected state and a linked panel', () => {
    render(<Harness />)
    expect(screen.getByRole('tablist', { name: 'Sections' })).toBeTruthy()
    expect(screen.getAllByRole('tab').map((t) => t.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false'])
    const panel = screen.getByRole('tabpanel')
    expect(panel.getAttribute('aria-labelledby')).toBe(tab('One').id)
    expect(tab('One').getAttribute('aria-controls')).toBe(panel.id)
    expect(tab('Two').getAttribute('aria-controls')).toBeNull()
    expect(panel.textContent).toBe('Panel one')
  })

  it('has a single tab stop (roving tabindex)', () => {
    render(<Harness initial="two" />)
    expect(screen.getAllByRole('tab').map((t) => t.tabIndex)).toEqual([-1, 0, -1])
  })

  it('selects a tab on click', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(tab('Three'))
    expect(tab('Three').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tabpanel').textContent).toBe('Panel three')
  })

  it('moves and selects with arrow keys (wrapping), Home and End', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    tab('One').focus()

    await user.keyboard('{ArrowRight}')
    expect(document.activeElement).toBe(tab('Two'))
    expect(tab('Two').getAttribute('aria-selected')).toBe('true')

    await user.keyboard('{ArrowRight}{ArrowRight}')
    expect(document.activeElement).toBe(tab('One')) // wrapped around

    await user.keyboard('{ArrowLeft}')
    expect(document.activeElement).toBe(tab('Three'))

    await user.keyboard('{Home}')
    expect(tab('One').getAttribute('aria-selected')).toBe('true')
    await user.keyboard('{End}')
    expect(tab('Three').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tabpanel').textContent).toBe('Panel three')
  })

  it('Tab moves from the selected tab into the panel', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    tab('One').focus()
    await user.tab()
    expect(document.activeElement).toBe(screen.getByRole('tabpanel'))
  })
})
