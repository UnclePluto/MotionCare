import { describe, expect, it } from 'vitest'

import { createColorSequenceRound, evaluateColorSequenceAttempt } from './colorSequence'

describe('createColorSequenceRound', () => {
  it('creates a simple 3-step sequence from 3 colors', () => {
    const round = createColorSequenceRound('简单', () => 0)

    expect(round.colors).toEqual(['blue', 'green', 'yellow'])
    expect(round.sequence).toEqual(['blue', 'blue', 'blue'])
    expect(round.revealMs).toBe(900)
    expect(round.inputTimeoutMs).toBe(8000)
  })

  it('creates a difficult sequence with more colors and shorter timing', () => {
    const round = createColorSequenceRound('困难', () => 0.99)

    expect(round.colors).toEqual(['blue', 'green', 'yellow', 'red', 'teal'])
    expect(round.sequence.length).toBe(7)
    expect(round.revealMs).toBe(560)
    expect(round.inputTimeoutMs).toBe(5000)
  })

  it('keeps sequence tokens valid when random returns a negative value', () => {
    const round = createColorSequenceRound('简单', () => -1)

    expect(round.sequence).toHaveLength(3)
    expect(round.sequence.every((token) => round.colors.includes(token))).toBe(true)
  })

  it('keeps sequence tokens valid when random returns NaN', () => {
    const round = createColorSequenceRound('简单', () => Number.NaN)

    expect(round.sequence).toHaveLength(3)
    expect(round.sequence.every((token) => round.colors.includes(token))).toBe(true)
  })
})

describe('evaluateColorSequenceAttempt', () => {
  it('marks an exact sequence as correct', () => {
    expect(evaluateColorSequenceAttempt(['blue', 'green'], ['blue', 'green'])).toEqual({
      correct: true,
      expected: ['blue', 'green'],
      actual: ['blue', 'green'],
    })
  })

  it('marks wrong order as incorrect', () => {
    expect(evaluateColorSequenceAttempt(['blue', 'green'], ['green', 'blue']).correct).toBe(false)
  })
})
