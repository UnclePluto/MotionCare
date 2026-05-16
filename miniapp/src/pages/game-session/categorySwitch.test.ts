import { describe, expect, it } from 'vitest'

import { createCategorySwitchRound, evaluateCategorySwitchAttempt } from './categorySwitch'

function randomSequence(values: number[]) {
  let index = 0
  return () => values[Math.min(index++, values.length - 1)]
}

function expectUniqueOptions(options: string[]) {
  expect(new Set(options).size).toBe(options.length)
}

describe('createCategorySwitchRound', () => {
  it('creates a simple kind round with three options and long timeout', () => {
    const round = createCategorySwitchRound('简单', { random: () => 0 })

    expect(round.rule).toBe('kind')
    expect(round.ruleLabel).toBe('按物体类别选择')
    expect(round.item).toMatchObject({
      id: 'pineapple',
      label: '菠萝',
      kind: '水果',
    })
    expect(round.correctOption).toBe('水果')
    expect(round.options).toHaveLength(3)
    expect(round.options.filter((option) => option === round.correctOption)).toHaveLength(1)
    expectUniqueOptions(round.options)
    expect(round.timeoutMs).toBe(7000)
  })

  it('creates a medium round from kind or color rules', () => {
    const round = createCategorySwitchRound('中等', { random: () => 0.75 })

    expect(['kind', 'color']).toContain(round.rule)
    expect(round.options.length).toBeGreaterThanOrEqual(3)
    expect(round.options).toHaveLength(4)
    expect(round.options.filter((option) => option === round.correctOption)).toHaveLength(1)
    expectUniqueOptions(round.options)
    expect(round.timeoutMs).toBe(5500)
  })

  it('creates a difficult round from kind color or scene rules', () => {
    const round = createCategorySwitchRound('困难', { random: () => 0.99 })

    expect(['kind', 'color', 'scene']).toContain(round.rule)
    expect(round.options).toContain(round.correctOption)
    expect(round.options).toHaveLength(4)
    expect(round.options.filter((option) => option === round.correctOption)).toHaveLength(1)
    expectUniqueOptions(round.options)
    expect(round.timeoutMs).toBe(4200)
  })

  it('uses random to avoid keeping the correct option fixed at the first position', () => {
    const round = createCategorySwitchRound('简单', { random: randomSequence([0, 0, 0]) })

    expect(round.correctOption).toBe('水果')
    expect(round.options).toHaveLength(3)
    expect(round.options).toContain(round.correctOption)
    expect(round.options[0]).not.toBe(round.correctOption)
  })

  it('switches medium rules away from the previous rule when possible', () => {
    const previousRule = 'kind'
    const round = createCategorySwitchRound('中等', { previousRule, random: randomSequence([0, 0, 0]) })

    expect(round.rule).not.toBe(previousRule)
  })

  it('switches difficult rules away from the previous rule when possible', () => {
    const previousRule = 'scene'
    const round = createCategorySwitchRound('困难', { previousRule, random: randomSequence([0, 0.99, 0]) })

    expect(round.rule).not.toBe(previousRule)
  })

  it('keeps simple rounds on kind even when previous rule is provided', () => {
    const round = createCategorySwitchRound('简单', { previousRule: 'kind', random: () => 0 })

    expect(round.rule).toBe('kind')
  })
})

describe('evaluateCategorySwitchAttempt', () => {
  const round = createCategorySwitchRound('简单', { random: () => 0 })

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
