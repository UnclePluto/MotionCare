import { describe, expect, it } from 'vitest'

import {
  buildMotionTrainingCameraUrl,
  buildMotionTrainingGuideUrl,
  buildMotionTrainingPreviewUrl,
  buildMotionTrainingUploadUrl,
  resolveMotionTrainingAction
} from '../../features/motion-training/action'
import { OFFICIAL_MOTION_SOURCE_KEYS } from '../../features/motion-training/catalog'
import type { CurrentPrescription } from '../../types/patientApp'
import { actionButtonLabel, actionEntryUrl } from './actionRouting'

describe('prescription action routing', () => {
  it.each(OFFICIAL_MOTION_SOURCE_KEYS)('routes %s to motion training', (sourceKey) => {
    const action = { id: 42, source_key: sourceKey, internal_type: 'motion' as const }

    expect(actionEntryUrl(action)).toBe('/pages/motion-training/index?actionId=42')
    expect(actionButtonLabel(action)).toBe('开始跟练')
  })

  it('keeps non-official motion actions on the normal training page', () => {
    const action = {
      id: 43,
      source_key: 'motion-resistance-unknown',
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

  it('resolves only the matching official motion action', () => {
    const prescription: CurrentPrescription = {
      id: 1,
      version: 1,
      status: 'active',
      effective_at: null,
      week_start: '2026-08-17',
      week_end: '2026-08-23',
      actions: [
        {
          id: 42,
          action_library_item: 4,
          source_key: 'motion-resistance-row',
          action_name: '划船',
          training_type: '运动',
          internal_type: 'motion',
          action_type: '阻力训练',
          action_instruction: '保持背部稳定',
          video_url: '',
          has_ai_supervision: false,
          weekly_frequency: '3 次/周',
          duration_minutes: 10,
          weekly_target_count: 3,
          weekly_completed_count: 0,
          difficulty: '普通',
          notes: '',
          sort_order: 1,
          recent_record: null
        },
        {
          id: 43,
          action_library_item: 5,
          source_key: 'motion-resistance-unknown',
          action_name: '未知动作',
          training_type: '运动',
          internal_type: 'motion',
          action_type: '阻力训练',
          action_instruction: '',
          video_url: '',
          has_ai_supervision: false,
          weekly_frequency: '3 次/周',
          duration_minutes: 10,
          weekly_target_count: 3,
          weekly_completed_count: 0,
          difficulty: '普通',
          notes: '',
          sort_order: 2,
          recent_record: null
        },
        {
          id: 44,
          action_library_item: 6,
          source_key: 'motion-resistance-shoulder-press',
          action_name: '肩部推举',
          training_type: '游戏',
          internal_type: 'game',
          action_type: '游戏',
          action_instruction: '',
          video_url: '',
          has_ai_supervision: false,
          weekly_frequency: '3 次/周',
          duration_minutes: 10,
          weekly_target_count: 3,
          weekly_completed_count: 0,
          difficulty: '普通',
          notes: '',
          sort_order: 3,
          recent_record: null
        }
      ]
    }

    expect(resolveMotionTrainingAction(prescription, 42)).toMatchObject({ id: 42 })
    expect(resolveMotionTrainingAction(prescription, 43)).toBeNull()
    expect(resolveMotionTrainingAction(prescription, 44)).toBeNull()
    expect(resolveMotionTrainingAction(prescription, 999)).toBeNull()
  })

  it('builds motion training urls from the action id', () => {
    expect(buildMotionTrainingGuideUrl(42)).toBe('/pages/motion-training/index?actionId=42')
    expect(buildMotionTrainingCameraUrl(42)).toBe('/pages/motion-training/camera?actionId=42')
    expect(buildMotionTrainingPreviewUrl(42)).toBe('/pages/motion-training/preview?actionId=42')
    expect(buildMotionTrainingUploadUrl()).toBe('/pages/motion-training/upload')
  })
})
