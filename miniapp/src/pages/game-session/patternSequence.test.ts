import { describe, expect, it } from 'vitest'

import { createPatternSequenceRound, evaluatePatternSequenceAttempt } from './patternSequence'

describe('createPatternSequenceRound', () => {
  it('creates a simple 3-step sequence from 3 patterns', () => {
    const round = createPatternSequenceRound('简单', () => 0)

    expect(round.patterns.map((pattern) => pattern.id)).toEqual(['sun', 'coconut', 'boat'])
    expect(round.sequence.map((item) => item.id)).toEqual(['sun', 'sun', 'sun'])
    expect(round.sequence[0]).toMatchObject({
      imageKey: 'pattern_sun',
      label: '太阳',
    })
    expect(round.patterns.every((pattern) => !('imageSrc' in pattern))).toBe(true)
    expect(round.revealMs).toBe(2000)
    expect(round.inputTimeoutMs).toBe(8000)
  })

  it('creates a difficult sequence with five patterns and five two-second steps', () => {
    const round = createPatternSequenceRound('困难', () => 0.99)

    expect(round.patterns.map((pattern) => pattern.id)).toEqual(['sun', 'coconut', 'boat', 'lighthouse', 'shell'])
    expect(round.sequence).toHaveLength(5)
    expect(round.revealMs).toBe(2000)
    expect(round.inputTimeoutMs).toBe(5000)
  })

  it('always uses four steps for medium difficulty', () => {
    for (const value of [0, 0.5, 0.99999]) {
      const round = createPatternSequenceRound('中等', () => value)
      expect(round.patterns).toHaveLength(4)
      expect(round.sequence).toHaveLength(4)
      expect(round.revealMs).toBe(2000)
    }
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
