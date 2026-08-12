import { describe, expect, it } from 'vitest'

import { createDemoCurrentPrescription, createDemoHomeData } from './data'

const expectedGames = [
  ['game-memory-color-sequence', '颜色顺序记忆'],
  ['game-memory-pattern-sequence', '图案顺序记忆'],
  ['game-executive-inhibition', '反应抑制'],
  ['game-executive-category-switch', '分类切换'],
  ['game-audiovisual-sound-discrimination', '声音辨别'],
  ['game-audiovisual-puzzle', '拼图'],
] as const

describe('固定演示数据', () => {
  it('每次创建完全独立的运动计划与动作对象', () => {
    const first = createDemoCurrentPrescription()
    const second = createDemoCurrentPrescription()

    expect(first).not.toBe(second)
    expect(first.actions).not.toBe(second.actions)
    expect(first.actions).toHaveLength(second.actions.length)
    first.actions.forEach((action, index) => {
      expect(action).not.toBe(second.actions[index])
    })
  })

  it('每次创建独立的六游戏体验计划', () => {
    const first = createDemoHomeData()
    const second = createDemoHomeData()

    expect(first.patient.name).toBe('用户01')
    expect(first.project.name).toBe('功能展示')
    expect(first.current_prescription?.actions.map((action) => [action.source_key, action.action_name]))
      .toEqual(expectedGames)
    expect(first.current_prescription?.actions.every((action) => (
      action.internal_type === 'game' && action.duration_minutes === 1 && action.difficulty === '简单'
    ))).toBe(true)
    expect(first).not.toBe(second)
    expect(first.current_prescription).not.toBe(second.current_prescription)
    expect(first.current_prescription?.actions).not.toBe(second.current_prescription?.actions)
  })
})
