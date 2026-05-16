import { describe, expect, it } from 'vitest'

import { createPatternSequenceRound, evaluatePatternSequenceAttempt } from './patternSequence'

describe('createPatternSequenceRound', () => {
  it('creates a simple 3-step sequence from 3 patterns', () => {
    const round = createPatternSequenceRound('简单', () => 0)

    expect(round.patterns.map((pattern) => pattern.id)).toEqual(['sun', 'coconut', 'boat'])
    expect(round.sequence.map((item) => item.id)).toEqual(['sun', 'sun', 'sun'])
    expect(round.sequence[0]).toMatchObject({
      imageSrc: '/assets/images/game-session/pattern_sun.svg',
      label: '太阳',
    })
    expect(round.revealMs).toBe(900)
    expect(round.inputTimeoutMs).toBe(8000)
  })

  it('creates a difficult sequence with 5 patterns, 7 steps, and shorter timing', () => {
    const round = createPatternSequenceRound('困难', () => 0.99)

    expect(round.patterns.map((pattern) => pattern.id)).toEqual(['sun', 'coconut', 'boat', 'lighthouse', 'shell'])
    expect(round.sequence).toHaveLength(7)
    expect(round.revealMs).toBe(560)
    expect(round.inputTimeoutMs).toBe(5000)
  })
})

describe('evaluatePatternSequenceAttempt', () => {
  it('marks an exact sequence as correct', () => {
    expect(evaluatePatternSequenceAttempt(['sun', 'boat'], ['sun', 'boat'])).toEqual({
      correct: true,
      expected: ['sun', 'boat'],
      actual: ['sun', 'boat'],
    })
  })

  it('marks wrong order as incorrect', () => {
    expect(evaluatePatternSequenceAttempt(['sun', 'boat'], ['boat', 'sun']).correct).toBe(false)
  })
})
