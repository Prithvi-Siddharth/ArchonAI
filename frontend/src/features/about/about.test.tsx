/** The About page: tabs, version, links, and its place in the sidebar. No network is involved. */
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { findPageMeta, NAV_SECTIONS } from '@/components/layout/navigation'

import pkg from '../../../package.json'
import { AboutPage } from './AboutPage'
import { APP_VERSION, parseAboutTab, POLICY_UPDATED } from './about-tabs'

function Where() {
  const location = useLocation()
  return <p data-testid="where">{`${location.pathname}${location.search}`}</p>
}

function renderPage(path = '/about') {
  const router = createMemoryRouter(
    [
      {
        path: '/about',
        element: (
          <>
            <AboutPage />
            <Where />
          </>
        ),
      },
      { path: '*', element: <p>Elsewhere</p> },
    ],
    { initialEntries: [path] },
  )
  render(<RouterProvider router={router} />)
  return { router, user: userEvent.setup() }
}

const panel = () => within(screen.getByRole('tabpanel'))

afterEach(cleanup)

describe('About page', () => {
  it('opens on About, with the four tabs in order', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'About ArchonAI' })).toBeTruthy()
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['About', 'How to use', 'Privacy', 'Terms'])
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')
    expect(panel().getByText('What ArchonAI is')).toBeTruthy()
    expect(document.title).toBe('About · ArchonAI')
  })

  it('shows the version, taken from package.json, and the license', () => {
    renderPage()
    expect(APP_VERSION).toBe(pkg.version)
    expect(APP_VERSION).toMatch(/^\d+\.\d+\.\d+$/)
    expect(screen.getByTestId('app-version').textContent).toBe(`v${pkg.version}`)
    const card = within(screen.getByRole('group', { name: 'Version' }))
    expect(card.getByText('MIT, free to use and modify')).toBeTruthy()
    expect(card.getByText('LangGraph')).toBeTruthy()
  })

  it('How to use lists the steps in order and links to the right pages', async () => {
    const { user } = renderPage()
    await user.click(screen.getByRole('tab', { name: 'How to use' }))
    const steps = within(screen.getByRole('list', { name: 'Steps' })).getAllByRole('listitem')
    expect(steps).toHaveLength(6)
    expect(steps[0].textContent).toContain('Create an account or sign in')
    expect(steps[5].textContent).toContain('Find it again later')
    const hrefs = (name: string) => panel().getByRole('link', { name }).getAttribute('href')
    expect(hrefs('Bring Your Own Key')).toBe('/byok')
    expect(hrefs('New Architecture')).toBe('/architectures/new')
    expect(hrefs('Activity')).toBe('/activity')
    expect(hrefs('Architecture History')).toBe('/architectures/history')
    expect(panel().getByText('Writing a good request')).toBeTruthy()
    expect(panel().getByText('If a job fails')).toBeTruthy()
  })

  it('Privacy states what is stored, what is shared, and the limits of the app', async () => {
    const { user } = renderPage()
    await user.click(screen.getByRole('tab', { name: 'Privacy' }))
    const text = screen.getByRole('tabpanel').textContent ?? ''
    expect(text).toContain(`Last updated ${POLICY_UPDATED}`)
    expect(text).toContain('The password itself is never stored')
    expect(text).toContain('encrypted before it is stored')
    expect(text).toContain('No advertising, analytics or tracking cookies')
    expect(text).toContain('Deleting your account or your jobs is not available in the app yet')
    for (const heading of ['What is stored', 'What is sent to other services', 'Cookies and browser storage', 'Who can see your data', 'Your choices']) {
      expect(panel().getByRole('heading', { name: heading })).toBeTruthy()
    }
    expect(panel().getByRole('link', { name: 'Bring Your Own Key' }).getAttribute('href')).toBe('/byok')
  })

  it('Terms covers estimates, AI output, the key, availability and the license', async () => {
    const { user } = renderPage()
    await user.click(screen.getByRole('tab', { name: 'Terms' }))
    const text = screen.getByRole('tabpanel').textContent ?? ''
    expect(text).toContain(`Last updated ${POLICY_UPDATED}`)
    expect(text).toContain('Cost figures are educational estimates, not AWS quotes')
    expect(text).toContain('They are not professional advice')
    expect(text).toContain('MIT license')
    expect(text).toContain('without warranty of any kind')
    expect(panel().getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Terms of use',
      'Designs and costs are suggestions',
      'Your requests and your key',
      'Fair use',
      'Availability',
      'License and warranty',
    ])
  })

  it('keeps the tab in the URL, so a link opens it and Back-free reloads keep it', async () => {
    const { user } = renderPage('/about?tab=privacy')
    expect(screen.getByRole('tab', { name: 'Privacy' }).getAttribute('aria-selected')).toBe('true')
    await user.click(screen.getByRole('tab', { name: 'Terms' }))
    expect(screen.getByTestId('where').textContent).toBe('/about?tab=terms')
  })

  it('falls back to About for an unknown tab', () => {
    renderPage('/about?tab=nonsense')
    expect(screen.getByRole('tab', { name: 'About' }).getAttribute('aria-selected')).toBe('true')
    expect(parseAboutTab(null)).toBe('about')
    expect(parseAboutTab('privacy')).toBe('privacy')
  })

  it('arrow keys move between the tabs', async () => {
    const { user } = renderPage()
    screen.getByRole('tab', { name: 'About' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'How to use' }).getAttribute('aria-selected')).toBe('true')
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Terms' }).getAttribute('aria-selected')).toBe('true')
  })
})

describe('About in the sidebar', () => {
  it('has its own Help section, after System', () => {
    expect(NAV_SECTIONS.map((section) => section.title)).toEqual(['Workspace', 'System', 'Help'])
    const help = NAV_SECTIONS.find((section) => section.title === 'Help')
    expect(help?.items.map((i) => [i.label, i.to])).toEqual([
      ['About', '/about'],
      ['Creator', '/creator'],
    ])
    const system = NAV_SECTIONS.find((section) => section.title === 'System')
    expect(system?.items.map((i) => i.label)).toEqual(['Bring Your Own Key', 'Settings'])
    expect(findPageMeta('/about')).toEqual({ section: 'Help', label: 'About' })
  })
})
