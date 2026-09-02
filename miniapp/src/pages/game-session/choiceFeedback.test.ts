import { describe, expect, it } from 'vitest'

import { choiceFeedbackState } from './choiceFeedback'

describe('choiceFeedbackState', () => {
  it('marks only the selected numeric option', () => {
    const outcome = { selected: 2, correct: false }
    expect(choiceFeedbackState(1, outcome)).toBe('idle')
    expect(choiceFeedbackState(2, outcome)).toBe('wrong')
  })

  it('marks a selected string option correct', () => {
    expect(choiceFeedbackState('水果', { selected: '水果', correct: true })).toBe('correct')
    expect(choiceFeedbackState('动物', { selected: '水果', correct: true })).toBe('idle')
  })

  it('keeps every option idle before an answer', () => {
    expect(choiceFeedbackState('水果', null)).toBe('idle')
  })
})
