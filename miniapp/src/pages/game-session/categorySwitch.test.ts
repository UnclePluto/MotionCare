import { describe, expect, it } from 'vitest'

import { createCategorySwitchRound, evaluateCategorySwitchAttempt } from './categorySwitch'

describe('createCategorySwitchRound', () => {
  it('creates a simple kind round with three options and long timeout', () => {
    const round = createCategorySwitchRound('简单', () => 0)

    expect(round.rule).toBe('kind')
    expect(round.ruleLabel).toBe('按物体类别选择')
    expect(round.item).toMatchObject({
      id: 'pineapple',
      label: '菠萝',
      kind: '水果',
    })
    expect(round.correctOption).toBe('水果')
    expect(round.options).toEqual(['水果', '动物', '交通'])
    expect(round.timeoutMs).toBe(7000)
  })

  it('creates a medium round from kind or color rules', () => {
    const round = createCategorySwitchRound('中等', () => 0.75)

    expect(['kind', 'color']).toContain(round.rule)
    expect(round.options.length).toBeGreaterThanOrEqual(3)
    expect(round.timeoutMs).toBe(5500)
  })

  it('creates a difficult round from kind color or scene rules', () => {
    const round = createCategorySwitchRound('困难', () => 0.99)

    expect(['kind', 'color', 'scene']).toContain(round.rule)
    expect(round.options).toContain(round.correctOption)
    expect(round.timeoutMs).toBe(4200)
  })
})

describe('evaluateCategorySwitchAttempt', () => {
  const round = createCategorySwitchRound('简单', () => 0)

  it('marks the correct option as correct', () => {
    expect(evaluateCategorySwitchAttempt(round, '水果')).toEqual({
      correct: true,
      correctOption: '水果',
      selectedOption: '水果',
    })
  })

  it('marks a different option as incorrect', () => {
    expect(evaluateCategorySwitchAttempt(round, '动物')).toEqual({
      correct: false,
      correctOption: '水果',
      selectedOption: '动物',
    })
  })
})
