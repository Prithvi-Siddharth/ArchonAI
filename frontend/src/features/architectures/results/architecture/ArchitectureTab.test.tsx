import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import { REAL_ARCHITECTURE_BACKWARD, REAL_ARCHITECTURE_COMBINED } from '@/test/real-architectures'
import type { Architecture } from '@/types/api'

import { ArchitectureTab } from './ArchitectureTab'

function renderTab(architecture: Architecture) {
  render(<ArchitectureTab result={makeResult({ architecture })} />)
  return userEvent.setup()
}

const diagram = () => screen.getByRole('group', { name: /Data-flow diagram/ })
const node = (label: string) => within(diagram()).getByRole('button', { name: label })
const edges = () => [...document.querySelectorAll('[data-edge]')] as HTMLElement[]
const edgeStates = () => Object.fromEntries(edges().map((e) => [e.dataset.step, e.dataset.state]))

afterEach(() => cleanup())

describe('ArchitectureTab with real data', () => {
  it('shows the summary, every endpoint as a node and every step as an arrow', () => {
    renderTab(REAL_ARCHITECTURE_COMBINED)
    expect(screen.getByText(REAL_ARCHITECTURE_COMBINED.summary)).toBeTruthy()
    expect(within(diagram()).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'User browser', 'CloudFront + WAF', 'Route 53 + ALB', 'ALB', 'ECS Fargate', 'DynamoDB + ElastiCache', 'Aurora + SQS',
    ])
    expect(edges().map((e) => [e.dataset.step, e.dataset.from, e.dataset.to])).toEqual(
      REAL_ARCHITECTURE_COMBINED.data_flow.map((s) => [String(s.step), s.source, s.destination]),
    )
    expect(edges().map((e) => e.querySelector('text')?.textContent)).toEqual(['1', '2', '3', '4', '5'])
    expect(edges().every((e) => e.querySelector('path')?.getAttribute('marker-end')?.startsWith('url(#'))).toBe(true)
  })

  it('lists every original step in order, with descriptions', () => {
    renderTab(REAL_ARCHITECTURE_COMBINED)
    const items = within(screen.getByRole('list', { name: 'Data-flow steps' })).getAllByRole('listitem')
    expect(items).toHaveLength(REAL_ARCHITECTURE_COMBINED.data_flow.length)
    REAL_ARCHITECTURE_COMBINED.data_flow.forEach((s, i) => {
      expect(items[i].textContent).toContain(`Step ${s.step}: ${s.source}`)
      expect(items[i].textContent).toContain(s.destination)
      expect(items[i].textContent).toContain(s.description)
    })
  })

  it('selecting an endpoint highlights it and its steps, and lists incoming and outgoing steps', async () => {
    const user = renderTab(REAL_ARCHITECTURE_COMBINED)
    await user.click(node('ECS Fargate'))

    expect(node('ECS Fargate').getAttribute('aria-pressed')).toBe('true')
    expect(edgeStates()).toEqual({ 1: 'dimmed', 2: 'dimmed', 3: 'highlighted', 4: 'highlighted', 5: 'highlighted' })
    expect(node('User browser').className).toContain('opacity-40')
    expect(node('ALB').className).not.toContain('opacity-40')

    const details = screen.getByRole('heading', { name: 'ECS Fargate' }).closest('div[aria-live]') as HTMLElement
    expect(within(details).getByText('Incoming steps (1)')).toBeTruthy()
    expect(within(details).getByText('from ALB')).toBeTruthy()
    expect(within(details).getByText('Outgoing steps (2)')).toBeTruthy()
    expect(within(details).getByText('to DynamoDB + ElastiCache')).toBeTruthy()
    expect(within(details).getByText(REAL_ARCHITECTURE_COMBINED.data_flow[4].description)).toBeTruthy()
  })

  it('labels name matches as possible, never as confirmed', async () => {
    const user = renderTab(REAL_ARCHITECTURE_COMBINED)
    await user.click(node('Aurora + SQS'))
    expect(screen.getByText(/Matched by name only/)).toBeTruthy()
    expect(screen.getByText('Possible match: Amazon SQS')).toBeTruthy()
    await user.click(node('User browser'))
    expect(screen.getByText('No service name resembles this label.')).toBeTruthy()
  })

  it('clears the selection with the button, by clicking again, or with Escape', async () => {
    const user = renderTab(REAL_ARCHITECTURE_COMBINED)
    await user.click(node('ALB'))
    await user.click(screen.getByRole('button', { name: /Clear selection/ }))
    expect(node('ALB').getAttribute('aria-pressed')).toBe('false')
    expect(Object.values(edgeStates()).every((s) => s === 'default')).toBe(true)

    await user.click(node('ALB'))
    await user.click(node('ALB'))
    expect(node('ALB').getAttribute('aria-pressed')).toBe('false')

    await user.click(node('ALB'))
    await user.keyboard('{Escape}')
    expect(node('ALB').getAttribute('aria-pressed')).toBe('false')
  })

  it('is keyboard operable: Tab between endpoints, Enter or Space selects', async () => {
    const user = renderTab(REAL_ARCHITECTURE_COMBINED)
    node('User browser').focus()
    await user.tab()
    expect(document.activeElement).toBe(node('CloudFront + WAF'))
    await user.keyboard('{Enter}')
    expect(node('CloudFront + WAF').getAttribute('aria-pressed')).toBe('true')
    await user.tab()
    await user.keyboard(' ')
    expect(node('Route 53 + ALB').getAttribute('aria-pressed')).toBe('true')
    expect(node('CloudFront + WAF').getAttribute('aria-pressed')).toBe('false')
  })

  it('marks a step back to an earlier endpoint as a back edge', () => {
    renderTab(REAL_ARCHITECTURE_BACKWARD)
    expect(edges().filter((e) => e.dataset.kind === 'back').map((e) => [e.dataset.from, e.dataset.to])).toEqual([['ECS (Fargate) + Lambda', 'User']])
  })

  it('groups all services by category, with all four fields, including services no step names', () => {
    renderTab(REAL_ARCHITECTURE_COMBINED)
    const section = screen.getByRole('region', { name: 'AWS services' })
    for (const service of REAL_ARCHITECTURE_COMBINED.services) {
      const card = within(section).getByRole('heading', { name: service.name }).closest('li') as HTMLElement
      expect(card.textContent).toContain(service.category)
      expect(card.textContent).toContain(service.purpose)
      expect(card.textContent).toContain(service.justification)
    }
    // "Amazon S3" is not named by any data-flow step, yet it is listed.
    expect(REAL_ARCHITECTURE_COMBINED.data_flow.some((s) => /S3/.test(s.source + s.destination))).toBe(false)
    expect(within(section).getByRole('heading', { name: 'Amazon S3' })).toBeTruthy()
    // Two "Database" services share one group.
    expect(within(section).getByRole('heading', { name: /^Database/ }).textContent).toBe('Database2')
  })
})

describe('ArchitectureTab empty states', () => {
  it('shows an empty state instead of a diagram when there is no data flow', () => {
    renderTab({ ...REAL_ARCHITECTURE_COMBINED, data_flow: [] })
    expect(screen.getByText('No data flow recorded')).toBeTruthy()
    expect(screen.queryByRole('group', { name: /Data-flow diagram/ })).toBeNull()
    expect(screen.queryByRole('list', { name: 'Data-flow steps' })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Amazon S3' })).toBeTruthy() // services still shown
  })

  it('shows an empty state when there are no services', () => {
    renderTab({ ...REAL_ARCHITECTURE_COMBINED, services: [] })
    expect(screen.getByText('No services listed')).toBeTruthy()
    expect(screen.getByRole('group', { name: /Data-flow diagram/ })).toBeTruthy()
  })
})
