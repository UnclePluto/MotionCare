import { describe, expect, it } from 'vitest'

import { actionButtonLabel, actionEntryUrl } from './actionRouting'

describe('处方动作路由', () => {
  it('肩部推举进入录像跟练页', () => {
    const action = { id: 42, source_key: 'motion-resistance-shoulder-press', internal_type: 'motion' as const }
    expect(actionEntryUrl(action)).toBe('/pages/shoulder-press/index?actionId=42')
    expect(actionButtonLabel(action)).toBe('开始跟练')
  })

  it('其它动作保留原入口', () => {
    expect(actionEntryUrl({ id: 43, source_key: null, internal_type: 'motion' })).toBe(
      '/pages/training/index?actionId=43',
    )
  })
})
