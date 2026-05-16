import { describe, expect, it } from 'vitest'

import { createInhibitionRound, evaluateInhibitionAttempt } from './inhibition'

describe('createInhibitionRound', () => {
  it('creates a simple four-option round with one odd number', () => {
    const round = createInhibitionRound('简单', () => 0)

    expect(round.options).toEqual(['2', '1', '1', '1'])
    expect(round.correctIndex).toBe(0)
    expect(round.timeoutMs).toBe(7000)
  })

  it('creates a difficult nine-option round', () => {
    const round = createInhibitionRound('困难', () => 0.99)

    expect(round.options).toHaveLength(9)
    expect(round.correctIndex).toBeGreaterThanOrEqual(0)
    expect(round.correctIndex).toBeLessThan(9)
    expect(round.timeoutMs).toBe(4000)
  })

  it('keeps options and correct index valid when random returns a negative value', () => {
    const round = createInhibitionRound('简单', () => -1)

    expect(round.correctIndex).toBeGreaterThanOrEqual(0)
    expect(round.correctIndex).toBeLessThan(round.options.length)
    expect(round.options.every((option) => /^[1-9]$/.test(option))).toBe(true)
  })

  it('keeps options and correct index valid when random returns NaN', () => {
    const round = createInhibitionRound('简单', () => Number.NaN)

    expect(round.correctIndex).toBeGreaterThanOrEqual(0)
    expect(round.correctIndex).toBeLessThan(round.options.length)
    expect(round.options.every((option) => /^[1-9]$/.test(option))).toBe(true)
  })
})

describe('evaluateInhibitionAttempt', () => {
  it('returns correct when selected index is the odd number', () => {
    expect(evaluateInhibitionAttempt({ correctIndex: 2 }, 2)).toEqual({
      correct: true,
      correctIndex: 2,
      selectedIndex: 2,
    })
  })

  it('returns incorrect when selected index is different', () => {
    expect(evaluateInhibitionAttempt({ correctIndex: 2 }, 1).correct).toBe(false)
  })
})
