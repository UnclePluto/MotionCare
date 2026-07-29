import { describe, expect, it } from 'vitest'

import { actionButtonLabel, actionEntryUrl } from './actionRouting'

describe('prescription action routing', () => {
  it('routes only the shoulder press source to the dedicated follow-along page', () => {
    const action = {
      id: 42,
      source_key: 'motion-resistance-shoulder-press',
      internal_type: 'motion' as const
    }

    expect(actionEntryUrl(action)).toBe('/pages/shoulder-press/index?actionId=42')
    expect(actionButtonLabel(action)).toBe('开始跟练')
  })

  it('keeps other motion actions on the normal training page', () => {
    const action = {
      id: 43,
      source_key: 'motion-resistance-row',
      internal_type: 'motion' as const
    }

    expect(actionEntryUrl(action)).toBe('/pages/training/index?actionId=43')
    expect(actionButtonLabel(action)).toBe('开始训练')
  })

  it('keeps game actions on the existing game session flow', () => {
    const action = {
      id: 44,
      source_key: 'game-memory-color-sequence',
      internal_type: 'game' as const
    }

    expect(actionEntryUrl(action)).toBe('/pages/game-session/index?actionId=44')
    expect(actionButtonLabel(action)).toBe('开始游戏')
  })
})
