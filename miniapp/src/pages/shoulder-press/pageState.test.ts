import { describe, expect, it } from 'vitest'

import type { CurrentPrescription } from '../../types/patientApp'
import {
  canStartShoulderPressRecording,
  computeShoulderPressEffectiveDuration,
  formatShoulderPressTimer,
  isServerSafeFinalizeStatus,
  loadOwnedPendingShoulderPressSession,
  nextShoulderPressPreviewVisibility,
  remainingShoulderPressSeconds,
  resolveShoulderPressAction,
  saveOwnedPendingShoulderPressSession,
  SHOULDER_PRESS_RECORDING_STOP_MS,
  shoulderPressUploadCounters,
  shouldAutoFinishShoulderPressTraining
} from './pageState'
import { PENDING_MOTION_TRAINING_SESSION_KEY } from '../../features/motion-training/session'
import { createPendingShoulderPressSession } from './session'

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

describe('shoulder press compatibility page state', () => {
  it('resolves the requested active official motion action', () => {
    expect(resolveShoulderPressAction(prescription(), 42)?.action_name).toBe('肩部推举')
    expect(resolveShoulderPressAction(prescription(), 99)).toBeNull()

    const anotherMotion = prescription()
    anotherMotion.actions[0].source_key = 'motion-resistance-row'
    expect(resolveShoulderPressAction(anotherMotion, 42)?.action_name).toBe('肩部推举')

    const wrongSource = prescription()
    wrongSource.actions[0].source_key = 'motion-unknown'
    expect(resolveShoulderPressAction(wrongSource, 42)).toBeNull()
  })

  it('allows recording only after both action and front camera are ready', () => {
    expect(canStartShoulderPressRecording({ actionReady: true, cameraReady: true, busy: false })).toBe(true)
    expect(canStartShoulderPressRecording({ actionReady: false, cameraReady: true, busy: false })).toBe(false)
    expect(canStartShoulderPressRecording({ actionReady: true, cameraReady: false, busy: false })).toBe(false)
    expect(canStartShoulderPressRecording({ actionReady: true, cameraReady: true, busy: true })).toBe(false)
  })

  it('keeps old owned-session aliases compatible with get/set storage only', () => {
    const pending = createPendingShoulderPressSession({
      actionId: 42,
      expectedDurationSeconds: 120,
      trainingDate: '2026-08-06',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })
    const values = new Map<string, unknown>([[PENDING_MOTION_TRAINING_SESSION_KEY, pending]])
    const storage = {
      getStorageSync: (key: string) => values.get(key),
      setStorageSync: (key: string, value: unknown) => values.set(key, value)
    }

    expect(storage).not.toHaveProperty('removeStorageSync')
    expect(loadOwnedPendingShoulderPressSession(storage, pending.clientSessionId)).toEqual(pending)
    expect(saveOwnedPendingShoulderPressSession(storage, {
      ...pending,
      lastError: '等待网络恢复'
    })).toMatchObject({ lastError: '等待网络恢复' })
  })

  it('computes a clamped prescription countdown from effective recording time', () => {
    expect(remainingShoulderPressSeconds(0, 120)).toBe(120)
    expect(remainingShoulderPressSeconds(30_001, 120)).toBe(90)
    expect(remainingShoulderPressSeconds(120_000, 120)).toBe(0)
    expect(remainingShoulderPressSeconds(150_000, 120)).toBe(0)
  })

  it('auto finishes at the prescription duration and retains the camera safety stop', () => {
    expect(shouldAutoFinishShoulderPressTraining({
      actualDurationMs: 119_999,
      expectedDurationSeconds: 120
    })).toBe(false)
    expect(shouldAutoFinishShoulderPressTraining({
      actualDurationMs: 120_000,
      expectedDurationSeconds: 120
    })).toBe(true)
    expect(shouldAutoFinishShoulderPressTraining({
      actualDurationMs: SHOULDER_PRESS_RECORDING_STOP_MS,
      expectedDurationSeconds: 2400
    })).toBe(true)
  })

  it('only changes preview visibility for a dominant horizontal swipe', () => {
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'visible', deltaX: 45, deltaY: 5
    })).toBe('hidden')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'hidden', deltaX: -45, deltaY: 5
    })).toBe('visible')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'visible', deltaX: 20, deltaY: 0
    })).toBe('visible')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'visible', deltaX: 45, deltaY: 60
    })).toBe('visible')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'visible', deltaX: 40, deltaY: 0
    })).toBe('hidden')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'hidden', deltaX: -40, deltaY: 0
    })).toBe('visible')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'visible', deltaX: 39, deltaY: 0
    })).toBe('visible')
    expect(nextShoulderPressPreviewVisibility({
      visibility: 'visible', deltaX: 40, deltaY: 40
    })).toBe('visible')
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
      nowMs: 1_801_000
    })).toBe(1_800_000)
  })

  it('formats the fixed-size recording timer', () => {
    expect(formatShoulderPressTimer(0)).toBe('00:00')
    expect(formatShoulderPressTimer(61_400)).toBe('01:01')
    expect(formatShoulderPressTimer(1_800_000)).toBe('30:00')
  })

  it('counts uploaded and pending segments for stable page status', () => {
    expect(shoulderPressUploadCounters([
      {
        index: 0,
        compressionState: 'compressed',
        savedFilePath: 'wxfile://store/0.mp4',
        durationMs: 30_000,
        sizeBytes: 1024,
        uploadState: 'uploaded'
      },
      {
        index: 1,
        compressionState: 'compressed',
        savedFilePath: 'wxfile://store/1.mp4',
        durationMs: 30_000,
        sizeBytes: 1024,
        uploadState: 'uploading'
      },
      {
        index: 2,
        compressionState: 'pending_compression',
        rawSavedFilePath: 'wxfile://store/raw-2.mp4',
        durationMs: 30_000
      }
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
