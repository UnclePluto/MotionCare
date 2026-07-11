import { describe, expect, it } from 'vitest'

import type { CurrentPrescription } from '../../types/patientApp'
import {
  canStartShoulderPressRecording,
  canCompleteShoulderPressTraining,
  computeShoulderPressEffectiveDuration,
  formatShoulderPressTimer,
  isServerSafeFinalizeStatus,
  resolveShoulderPressAction,
  shoulderPressUploadCounters,
  shouldAutoFinishShoulderPressTraining
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

  it('allows finishing only after the prescribed shoulder press duration', () => {
    expect(canCompleteShoulderPressTraining({
      actualDurationMs: 119_000,
      expectedDurationSeconds: 120
    })).toBe(false)
    expect(canCompleteShoulderPressTraining({
      actualDurationMs: 120_000,
      expectedDurationSeconds: 120
    })).toBe(true)
  })

  it('auto finishes at the hard ten minute limit', () => {
    expect(shouldAutoFinishShoulderPressTraining(599_999)).toBe(false)
    expect(shouldAutoFinishShoulderPressTraining(600_000)).toBe(true)
  })

  it('computes effective duration from the continuous recording anchor without double counting saved segments', () => {
    expect(computeShoulderPressEffectiveDuration({
      savedDurationMs: 30_000,
      recording: true,
      recordingBaseDurationMs: 0,
      recordingStartedAtMs: 1_000,
      nowMs: 61_000
    })).toBe(60_000)
    expect(computeShoulderPressEffectiveDuration({
      savedDurationMs: 30_000,
      recording: false,
      recordingBaseDurationMs: 0,
      recordingStartedAtMs: 0,
      nowMs: 80_000
    })).toBe(30_000)
    expect(computeShoulderPressEffectiveDuration({
      savedDurationMs: 30_000,
      recording: true,
      recordingBaseDurationMs: 30_000,
      recordingStartedAtMs: 100_000,
      nowMs: 120_000
    })).toBe(50_000)
    expect(computeShoulderPressEffectiveDuration({
      savedDurationMs: 30_000,
      recording: true,
      recordingBaseDurationMs: 0,
      recordingStartedAtMs: 1_000,
      nowMs: 601_000
    })).toBe(600_000)
  })

  it('formats the fixed-size recording timer', () => {
    expect(formatShoulderPressTimer(0)).toBe('00:00')
    expect(formatShoulderPressTimer(61_400)).toBe('01:01')
    expect(formatShoulderPressTimer(600_000)).toBe('10:00')
  })

  it('counts uploaded and pending segments for stable page status', () => {
    expect(shoulderPressUploadCounters([
      { uploadState: 'uploaded' },
      { uploadState: 'uploading' },
      { uploadState: 'pending' }
    ])).toEqual({ uploaded: 1, total: 3, percent: 33 })
  })

  it('treats queued server processing as safe final receipt but keeps failed states on page', () => {
    expect(isServerSafeFinalizeStatus('queued')).toBe(true)
    expect(isServerSafeFinalizeStatus('assembling')).toBe(true)
    expect(isServerSafeFinalizeStatus('uploading_qiniu')).toBe(true)
    expect(isServerSafeFinalizeStatus('attached')).toBe(true)
    expect(isServerSafeFinalizeStatus('failed')).toBe(false)
    expect(isServerSafeFinalizeStatus('expired')).toBe(false)
  })
})
