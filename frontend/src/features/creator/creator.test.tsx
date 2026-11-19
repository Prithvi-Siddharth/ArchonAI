/** The Creator page: name, contact details, profile links and photo. No network is involved. */
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { findPageMeta, NAV_SECTIONS } from '@/components/layout/navigation'

import { CREATOR, type CreatorInfo } from './creator-info'
import { CreatorCard, CreatorPage } from './CreatorPage'

afterEach(cleanup)

const FULL: CreatorInfo = { ...CREATOR, linkedin: 'https://www.linkedin.com/in/example-person/' }

describe('Creator page', () => {
  it('shows the creator’s name, role and photo', () => {
    render(<CreatorPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Creator' })).toBeTruthy()
    expect(screen.getByRole('heading', { level: 2, name: 'Manepalli Prithvi Siddharth' })).toBeTruthy()
    expect(screen.getByText('Creator of ArchonAI')).toBeTruthy()
    expect(screen.getByText(CREATOR.role)).toBeTruthy()
    const photo = screen.getByRole('img', { name: 'Portrait of Manepalli Prithvi Siddharth' })
    expect(photo.getAttribute('src')).toBeTruthy()
    expect(document.title).toBe('Creator · ArchonAI')
  })

  it('shows contact details as working links', () => {
    render(<CreatorCard info={FULL} />)
    const contact = within(screen.getByRole('list', { name: 'Contact details' }))
    expect(contact.getByRole('link', { name: FULL.email }).getAttribute('href')).toBe(`mailto:${FULL.email}`)
    // Spaces and punctuation are dropped from the tel: link, the shown text keeps them.
    expect(contact.getByRole('link', { name: FULL.phone }).getAttribute('href')).toBe('tel:+917032240742')
    expect(contact.getByText('Hyderabad, Telangana')).toBeTruthy()
  })

  it('opens GitHub and LinkedIn in a new tab, safely', () => {
    render(<CreatorCard info={FULL} />)
    for (const [name, href] of [
      ['GitHub', 'https://github.com/Prithvi-Siddharth'],
      ['LinkedIn', 'https://www.linkedin.com/in/example-person/'],
    ]) {
      const link = screen.getByRole('link', { name: new RegExp(`^${name}`) })
      expect(link.getAttribute('href')).toBe(href)
      expect(link.getAttribute('target')).toBe('_blank')
      expect(link.getAttribute('rel')).toBe('noopener noreferrer')
    }
  })

  it('hides a profile button until its URL is set, instead of showing a dead link', () => {
    render(<CreatorCard info={{ ...CREATOR, linkedin: '' }} />)
    expect(screen.getByRole('link', { name: /^GitHub/ })).toBeTruthy()
    expect(screen.queryByRole('link', { name: /LinkedIn/ })).toBeNull()
  })

  it('uses real addresses, not placeholders', () => {
    expect(CREATOR.email).toMatch(/^[^@\s]+@[^@\s]+\.[^@\s]+$/)
    expect(CREATOR.github).toMatch(/^https:\/\/github\.com\/[\w-]+$/)
    expect(CREATOR.linkedin === '' || /^https:\/\/([\w-]+\.)?linkedin\.com\/in\/[\w%-]+\/?$/.test(CREATOR.linkedin)).toBe(true)
  })
})

describe('Creator in the sidebar', () => {
  it('is in the Help section after About', () => {
    const help = NAV_SECTIONS.find((section) => section.title === 'Help')
    expect(help?.items.map((i) => [i.label, i.to])).toEqual([
      ['About', '/about'],
      ['Creator', '/creator'],
    ])
    expect(findPageMeta('/creator')).toEqual({ section: 'Help', label: 'Creator' })
  })
})
