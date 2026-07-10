import { describe, expect, it } from 'vitest'

import type { CurrentPrescription } from '../../types/patientApp'
import {
  canStartShoulderPressRecording,
  resolveShoulderPressAction,
  uploadStageStates
} from './pageState'

function prescription(): NonNullable<CurrentPrescription> {
  return {
    id: 1,
    version: 1,
    status: 'active',
    effective_at: '2026-07-10T00:00:00+08:00',
    week_start: '2026-07-06',
    week_end: '2026-07-12',
    actions: [{
      id: 42,
      action_library_item: 9,
      source_key: 'motion-resistance-shoulder-press',
      action_name: '肩部推举',
      training_type: '抗阻训练',
      internal_type: 'motion',
      action_type: '抗阻训练',
      action_instruction: '保持正面，缓慢推举。',
      video_url: 'https://cdn.example.com/demo.mp4',
      has_ai_supervision: true,
      weekly_frequency: '3',
      duration_minutes: 2,
      weekly_target_count: 3,
      weekly_completed_count: 0,
      difficulty: '简单',
      notes: '',
      sort_order: 1,
      recent_record: null
    }]
  }
}

describe('shoulder press page state', () => {
  it('resolves only the requested active shoulder press action', () => {
    expect(resolveShoulderPressAction(prescription(), 42)?.action_name).toBe('肩部推举')
    expect(resolveShoulderPressAction(prescription(), 99)).toBeNull()

    const wrongSource = prescription()
    wrongSource.actions[0].source_key = 'motion-resistance-row'
    expect(resolveShoulderPressAction(wrongSource, 42)).toBeNull()
  })

  it('allows recording only after both action and front camera are ready', () => {
    expect(canStartShoulderPressRecording({ actionReady: true, cameraReady: true, busy: false })).toBe(true)
    expect(canStartShoulderPressRecording({ actionReady: false, cameraReady: true, busy: false })).toBe(false)
    expect(canStartShoulderPressRecording({ actionReady: true, cameraReady: false, busy: false })).toBe(false)
    expect(canStartShoulderPressRecording({ actionReady: true, cameraReady: true, busy: true })).toBe(false)
  })

  it('derives credential, upload, and complete stage states from persisted progress', () => {
    expect(uploadStageStates({ hasIntent: false, hasHash: false, activePhase: 'credential' }))
      .toEqual(['active', 'pending', 'pending'])
    expect(uploadStageStates({ hasIntent: true, hasHash: false, activePhase: 'upload' }))
      .toEqual(['done', 'active', 'pending'])
    expect(uploadStageStates({ hasIntent: true, hasHash: true, activePhase: 'complete' }))
      .toEqual(['done', 'done', 'active'])
    expect(uploadStageStates({ hasIntent: true, hasHash: true, activePhase: null }))
      .toEqual(['done', 'done', 'pending'])
  })
})
