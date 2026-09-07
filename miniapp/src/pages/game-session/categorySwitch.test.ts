import { describe, expect, it } from 'vitest'

import { CATEGORY_ITEMS, createCategorySwitchRound, evaluateCategorySwitchAttempt } from './categorySwitch'

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
    expect(round.ruleLabel).toBe('请判断彩图中的物体属于哪个类别，并选出正确的选项')
    expect(round.item).toMatchObject({
      id: 'pineapple',
      label: '菠萝',
      imageKey: 'category_pineapple',
      kind: '水果',
    })
    expect('imageSrc' in round.item).toBe(false)
    expect(round.correctOption).toBe('水果')
    expect(round.options).toHaveLength(3)
    expect(round.options.filter((option) => option === round.correctOption)).toHaveLength(1)
    expectUniqueOptions(round.options)
    expect(round.timeoutMs).toBe(7000)
  })

  it('creates a medium kind round with four options', () => {
    const round = createCategorySwitchRound('中等', { random: () => 0.75 })

    expect(round.rule).toBe('kind')
    expect(round.options.length).toBeGreaterThanOrEqual(3)
    expect(round.options).toHaveLength(4)
    expect(round.options.filter((option) => option === round.correctOption)).toHaveLength(1)
    expectUniqueOptions(round.options)
    expect(round.timeoutMs).toBe(5500)
  })

  it('creates a difficult kind round with five options', () => {
    const round = createCategorySwitchRound('困难', { random: () => 0.99 })

    expect(round.rule).toBe('kind')
    expect(round.options).toContain(round.correctOption)
    expect(round.options).toHaveLength(5)
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

  it('keeps medium rounds on kind after another kind round', () => {
    const previousRule = 'kind'
    const round = createCategorySwitchRound('中等', { previousRule, random: randomSequence([0, 0, 0]) })

    expect(round.rule).toBe('kind')
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

  it('always asks for object categories with one matching answer at every difficulty', () => {
    ;(['简单', '中等', '困难'] as const).forEach((difficulty) => {
      for (const randomValue of [0, 0.25, 0.5, 0.75, 0.99]) {
        const round = createCategorySwitchRound(difficulty, { random: () => randomValue })
        expect(round.rule).toBe('kind')
        expect(round.correctOption).toBe(round.item.kind)
        expect(round.options.filter((option) => option === round.item.kind)).toHaveLength(1)
      }
    })
  })

  it('matches approved dominant colors for the five current images', () => {
    expect(Object.fromEntries(CATEGORY_ITEMS.map((item) => [item.id, item.color]))).toEqual({
      pineapple: '黄色',
      bird: '蓝色',
      train: '蓝色',
      drum: '红色',
      phone: '蓝色',
    })
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
