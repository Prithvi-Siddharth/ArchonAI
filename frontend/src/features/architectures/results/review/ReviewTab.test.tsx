import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { REAL_REVIEW_APPROVED, REAL_REVIEW_NOT_APPROVED, REAL_REVIEW_WITH_LOW, withReview, type ReviewFields } from '@/test/real-reviews'

import { ReviewTab } from './ReviewTab'
import { severityCounts } from './SeverityBadge'

const renderReview = (fields: ReviewFields) => render(<ReviewTab result={withReview(fields)} />)
const section = (title: string) => {
  const heading = screen.getByRole('heading', { name: title })
  return (heading.closest('section') ?? heading.closest('.rounded-lg')) as HTMLElement
}
const summary = () => Object.fromEntries(
  within(section('Review summary')).getAllByRole('term').map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]),
)

afterEach(() => cleanup())

describe('ReviewTab with real results', () => {
  it('not approved: summary, score, limit reached', () => {
    renderReview(REAL_REVIEW_NOT_APPROVED)
    expect(summary()).toEqual({
      'Critic decision': 'Not approved',
      'Critic score': '68/100',
      Validation: 'Passed0 issues',
      Revisions: '2 rounds · version 2Limit reached',
    })
    const score = section('Critic score')
    expect(within(score).getByText('68')).toBeTruthy()
    expect(within(score).getByRole('progressbar').getAttribute('aria-valuenow')).toBe('68')
    expect(within(score).getByText('Not approved by the critic')).toBeTruthy()
  })

  it('approved: summary and no limit badge', () => {
    renderReview(REAL_REVIEW_APPROVED)
    expect(summary()['Critic decision']).toBe('Approved')
    expect(summary()['Critic score']).toBe('82/100')
    expect(summary().Revisions).toBe('1 round · version 2')
    expect(within(section('Revision history')).getByText('Not reached')).toBeTruthy()
  })

  it('lists every strength, every required change and every issue with severity and category', () => {
    renderReview(REAL_REVIEW_NOT_APPROVED)
    const { critic_review: critic } = REAL_REVIEW_NOT_APPROVED
    expect(within(section('Strengths')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(critic.strengths)
    expect(within(section('Required changes')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(critic.required_changes)
    const items = within(screen.getByRole('list', { name: 'Critic issues' })).getAllByRole('listitem')
    expect(items.map((li) => [li.dataset.severity, li.querySelectorAll('.rounded-full')[1].textContent, li.querySelector('p')?.textContent])).toEqual(
      critic.issues.map((i) => [i.severity, i.category, i.issue]),
    )
    expect(screen.getByText('1 critical · 2 high · 1 medium, in the order the critic listed them.')).toBeTruthy()
  })

  it('distinguishes all four severities by text, not colour alone', () => {
    renderReview({
      ...REAL_REVIEW_WITH_LOW,
      critic_review: {
        ...REAL_REVIEW_WITH_LOW.critic_review,
        issues: [
          { issue: 'A', severity: 'critical', category: 'security' },
          { issue: 'B', severity: 'high', category: 'reliability' },
          { issue: 'C', severity: 'medium', category: 'scalability' },
          { issue: 'D', severity: 'low', category: 'cost' },
        ],
      },
    })
    const badges = [...document.querySelectorAll('[data-severity] > div > [data-severity]')] as HTMLElement[]
    expect(badges.map((b) => [b.dataset.severity, b.textContent])).toEqual([
      ['critical', 'Critical'],
      ['high', 'High'],
      ['medium', 'Medium'],
      ['low', 'Low'],
    ])
    expect(new Set(badges.map((b) => b.className)).size).toBe(4)
    expect(badges[0].querySelector('svg')).toBeTruthy()
    expect(badges[3].querySelector('svg')).toBeNull()
  })

  it('a real result with a low-severity issue shows it', () => {
    renderReview(REAL_REVIEW_WITH_LOW)
    expect(screen.getAllByText('Low').length).toBeGreaterThan(0)
  })

  it('validation passed with no issues: a clear, limited success state', () => {
    renderReview(REAL_REVIEW_NOT_APPROVED)
    const validation = section('Validation results')
    expect(within(validation).getByText('Passed')).toBeTruthy()
    expect(within(validation).getByText('No validation issues reported')).toBeTruthy()
    expect(within(validation).getByText(/only the rules it checks, not every possible AWS concern/)).toBeTruthy()
  })

  it('shows open recommendations separately from issues', () => {
    renderReview(REAL_REVIEW_NOT_APPROVED)
    const open = screen.getByRole('region', { name: 'Open recommendations' })
    expect(within(open).getAllByRole('listitem').map((li) => li.textContent)).toEqual(REAL_REVIEW_NOT_APPROVED.open_recommendations)
    expect(within(open).getByText(/does not include/)).toBeTruthy()
  })

  it('shows the revision history and the change log as returned, without dates or revision numbers', () => {
    renderReview(REAL_REVIEW_NOT_APPROVED)
    const history = section('Revision history')
    expect(within(history).getByText('Reached')).toBeTruthy()
    expect(within(history).getAllByRole('listitem').map((li) => li.textContent)).toEqual(REAL_REVIEW_NOT_APPROVED.change_log)
    expect(within(history).getByText(/does not record which revision or time/)).toBeTruthy()
  })
})

describe('ReviewTab edge cases', () => {
  const base = REAL_REVIEW_NOT_APPROVED

  it('validation failed with issues: rule, severity and message for each', () => {
    renderReview({
      ...base,
      validation_results: {
        passed: false,
        issues: [
          { rule: 'database_without_backups', message: 'Aurora has no backup configured.', severity: 'high' },
          { rule: 'missing_caching_layer', message: 'No cache in front of the catalog.', severity: 'medium' },
        ],
      },
    })
    expect(summary().Validation).toBe('Failed2 issues')
    const items = within(screen.getByRole('list', { name: 'Validation issues' })).getAllByRole('listitem')
    expect(items.map((li) => [li.dataset.severity, li.querySelector('code')?.textContent, li.querySelector('p')?.textContent])).toEqual([
      ['high', 'database_without_backups', 'Aurora has no backup configured.'],
      ['medium', 'missing_caching_layer', 'No cache in front of the catalog.'],
    ])
    expect(screen.queryByText('No validation issues reported')).toBeNull()
  })

  it('validation failed without listed issues says so', () => {
    renderReview({ ...base, validation_results: { passed: false, issues: [] } })
    expect(screen.getByText('Validation did not pass, but no specific issues were listed.')).toBeTruthy()
  })

  it('empty strengths, issues, required changes, open recommendations and change log', () => {
    renderReview({
      ...base,
      critic_review: { ...base.critic_review, strengths: [], issues: [], required_changes: [] },
      open_recommendations: [],
      change_log: [],
    })
    for (const text of ['No strengths listed', 'No issues raised', 'No required changes', 'No open recommendations', 'No change-log entries.']) {
      expect(screen.getByText(text)).toBeTruthy()
    }
  })

  it('severityCounts orders by severity and skips absent levels', () => {
    expect(severityCounts(['medium', 'critical', 'medium', 'low'])).toBe('1 critical · 2 medium · 1 low')
    expect(severityCounts([])).toBe('')
  })
})
