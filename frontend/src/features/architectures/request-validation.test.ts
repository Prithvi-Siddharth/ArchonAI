// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { REQUEST_MAX_LENGTH, REQUEST_MIN_LENGTH, requestLength, validateRequest } from './request-validation'

describe('request length rules (match the backend: trimmed, 10-4000)', () => {
  it('uses the backend limits', () => {
    expect([REQUEST_MIN_LENGTH, REQUEST_MAX_LENGTH]).toEqual([10, 4000])
  })

  it('counts trimmed text', () => {
    expect(requestLength('   0123456789   ')).toBe(10)
    expect(validateRequest('   0123456789   ')).toBeUndefined()
  })

  it('counts an emoji as one character, like Python', () => {
    const tenEmoji = '😀'.repeat(10)
    expect(tenEmoji.length).toBe(20) // JavaScript's own count
    expect(requestLength(tenEmoji)).toBe(10)
    expect(validateRequest('😀'.repeat(4000))).toBeUndefined()
  })

  it('asks for a description when the text is empty or blank', () => {
    expect(validateRequest('')).toBe('Describe the system you want to design.')
    expect(validateRequest(' \n\t ')).toBe('Describe the system you want to design.')
  })

  it('explains a too-short request with the current count', () => {
    expect(validateRequest('012345678')).toBe('Add a little more detail: at least 10 characters (currently 9).')
  })

  it('accepts 4000 characters and rejects 4001', () => {
    expect(validateRequest('x'.repeat(4000))).toBeUndefined()
    expect(validateRequest('x'.repeat(4001))).toBe(
      'Shorten the description to 4,000 characters or fewer (currently 4,001).',
    )
  })
})
