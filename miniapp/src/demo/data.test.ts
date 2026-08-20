import { describe, expect, it } from 'vitest'

import { createDemoCurrentPrescription, createDemoHomeData } from './data'
import type { MotionSourceKey } from '../features/motion-training/catalog'

const demoVideoUrls: Record<MotionSourceKey, string> = {
  'motion-aerobic-high-knee': 'https://signed.example.com/high-knee.mp4',
  'motion-balance-sit-stand': 'https://signed.example.com/sit-stand.mp4',
  'motion-resistance-row': 'https://signed.example.com/row.mp4',
  'motion-resistance-leg-kickback': 'https://signed.example.com/leg-kickback.mp4',
  'motion-resistance-shoulder-press': 'https://signed.example.com/shoulder-press.mp4',
}

const expectedActions = [
  ['game-memory-color-sequence', '颜色顺序记忆'],
  ['game-memory-pattern-sequence', '图案顺序记忆'],
  ['game-executive-inhibition', '反应抑制'],
  ['game-executive-category-switch', '分类切换'],
  ['game-audiovisual-sound-discrimination', '声音辨别'],
  ['game-audiovisual-puzzle', '拼图'],
  ['motion-aerobic-high-knee', '椰林步道模拟（原地高抬腿+摆臂）'],
  ['motion-balance-sit-stand', '坐站转移训练'],
  ['motion-resistance-row', '坐姿划船'],
  ['motion-resistance-leg-kickback', '腿部后踢'],
  ['motion-resistance-shoulder-press', '肩部推举'],
] as const

const expectedMotionIds: Record<MotionSourceKey, number> = {
  'motion-aerobic-high-knee': 888808,
  'motion-balance-sit-stand': 888809,
  'motion-resistance-row': 888810,
  'motion-resistance-leg-kickback': 888811,
  'motion-resistance-shoulder-press': 888807,
}

describe('固定演示数据', () => {
  it('每次创建完全独立的运动计划与动作对象', () => {
    const first = createDemoCurrentPrescription(demoVideoUrls)
    const second = createDemoCurrentPrescription(demoVideoUrls)

    expect(first).not.toBe(second)
    expect(first.actions).not.toBe(second.actions)
    expect(first.actions).toHaveLength(second.actions.length)
    first.actions.forEach((action, index) => {
      expect(action).not.toBe(second.actions[index])
    })
  })

  it('每次创建独立的六游戏加五动作体验计划', () => {
    const first = createDemoHomeData(demoVideoUrls)
    const second = createDemoHomeData(demoVideoUrls)
    const actions = first.current_prescription?.actions

    expect(first.patient.name).toBe('用户01')
    expect(first.project.name).toBe('功能展示')
    expect(actions?.map((action) => [action.source_key, action.action_name]))
      .toEqual(expectedActions)
    expect(actions?.slice(0, 6).every((action) => (
      action.internal_type === 'game' && action.duration_minutes === 1 && action.difficulty === '简单'
    ))).toBe(true)
    const motionActions = actions?.filter((action) => action.internal_type === 'motion') ?? []
    expect(motionActions).toHaveLength(5)
    motionActions.forEach((action) => {
      const sourceKey = action.source_key as MotionSourceKey
      expect(action).toMatchObject({
        id: expectedMotionIds[sourceKey],
        action_library_item: expectedMotionIds[sourceKey],
        duration_minutes: 10,
        weekly_target_count: 1,
        video_url: demoVideoUrls[sourceKey],
        video_unavailable: false,
      })
    })
    expect(first).not.toBe(second)
    expect(first.current_prescription).not.toBe(second.current_prescription)
    expect(first.current_prescription?.actions).not.toBe(second.current_prescription?.actions)
  })

  it('清单中缺失的动作视频明确标记为不可用', () => {
    const videoUrls = { ...demoVideoUrls }
    delete (videoUrls as Partial<Record<MotionSourceKey, string>>)['motion-resistance-row']

    const prescription = createDemoCurrentPrescription(videoUrls)
    const row = prescription.actions.find((action) => (
      action.source_key === 'motion-resistance-row'
    ))

    expect(row).toMatchObject({
      video_url: '',
      video_unavailable: true,
    })
  })
})
