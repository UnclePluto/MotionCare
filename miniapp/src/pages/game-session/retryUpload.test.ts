import { describe, expect, it, vi } from 'vitest'

import type { GameTrainingPayload } from './gameTypes'
import {
  PENDING_GAME_UPLOAD_KEY,
  type PendingGameUpload,
  RETRY_DELAYS_SECONDS,
  clearPendingGameUpload,
  loadPendingGameUpload,
  markRetryFailure,
  resetRetryWindowForLaunch,
  savePendingGameUpload,
} from './retryUpload'

function payload(): GameTrainingPayload {
  return {
    prescription_action: 100,
    training_date: '2026-05-16',
    status: 'completed',
    actual_duration_minutes: 10,
    score: 90,
    form_data: {
      accuracy_rate: 90,
      error_count: 1,
      difficulty: '中等',
      raw_detail: {
        game_code: 'game-memory-color-sequence',
        ended_by: 'timer',
        ended_early: false,
        prescribed_difficulty: '中等',
        difficulty_adjusted: false,
        difficulty_adjust_reason: '',
        upload_mode: 'direct',
        retry_count: 0,
        total_retry_count: 0,
        session_duration_seconds: 600,
        suggested_duration_minutes: 10,
        completed_units: 10,
        correct_units: 9,
      },
    },
    note: '',
  }
}

function memoryStorage() {
  const store = new Map<string, unknown>()
  return {
    getStorageSync: vi.fn((key: string) => store.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
    removeStorageSync: vi.fn((key: string) => store.delete(key)),
  }
}

function pending(overrides: Partial<PendingGameUpload> = {}): PendingGameUpload {
  return {
    payload: payload(),
    retry_count: 0,
    total_retry_count: 0,
    next_retry_at: 1000,
    last_error: '',
    created_at: 1000,
    retry_paused_until_next_launch: false,
    ...overrides,
  }
}

describe('pending game upload retry state', () => {
  it('stores one pending upload and clears it after success', () => {
    const storage = memoryStorage()

    savePendingGameUpload(storage, payload(), 1000)
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(100)

    clearPendingGameUpload(storage)
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('does not overwrite an existing valid pending upload', () => {
    const storage = memoryStorage()
    const firstPayload = payload()
    const secondPayload = { ...payload(), prescription_action: 200 }

    savePendingGameUpload(storage, firstPayload, 1000)
    const saved = savePendingGameUpload(storage, secondPayload, 2000)

    expect(saved.payload.prescription_action).toBe(100)
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(100)
    expect(storage.setStorageSync).toHaveBeenCalledTimes(1)
  })

  it('pauses after ten failures in one launch window', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)

    for (let index = 0; index < 10; index += 1) {
      markRetryFailure(storage, `失败 ${index + 1}`, 1000 + index * 1000)
    }

    const pending = loadPendingGameUpload(storage)
    expect(pending?.retry_count).toBe(10)
    expect(pending?.total_retry_count).toBe(10)
    expect(pending?.retry_paused_until_next_launch).toBe(true)
  })

  it('does not reset an unpaused pending upload on launch', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)
    markRetryFailure(storage, '网络失败', 5000)

    const beforeReset = loadPendingGameUpload(storage)
    resetRetryWindowForLaunch(storage)

    const afterReset = loadPendingGameUpload(storage)
    expect(afterReset?.retry_count).toBe(beforeReset?.retry_count)
    expect(afterReset?.next_retry_at).toBe(beforeReset?.next_retry_at)
    expect(afterReset?.retry_paused_until_next_launch).toBe(false)
  })

  it('resets paused current retry count on next launch but preserves total retry count', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)
    for (let index = 0; index < 10; index += 1) {
      markRetryFailure(storage, '网络失败', 1000)
    }

    resetRetryWindowForLaunch(storage)

    const pending = loadPendingGameUpload(storage)
    expect(pending?.retry_count).toBe(0)
    expect(pending?.total_retry_count).toBe(10)
    expect(pending?.retry_paused_until_next_launch).toBe(false)
  })

  it('schedules first retry after five seconds', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)

    const pending = markRetryFailure(storage, '网络失败', 2000)

    expect(pending?.retry_count).toBe(1)
    expect(pending?.total_retry_count).toBe(1)
    expect(pending?.next_retry_at).toBe(7000)
    expect(pending?.retry_paused_until_next_launch).toBe(false)
  })

  it('keeps retry state unchanged after the launch window is paused', () => {
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)

    for (let index = 0; index < 10; index += 1) {
      markRetryFailure(storage, '网络失败', 1000 + index * 1000)
    }
    const beforeExtraFailure = loadPendingGameUpload(storage)

    const afterExtraFailure = markRetryFailure(storage, '仍然失败', 20000)

    expect(afterExtraFailure?.retry_count).toBe(10)
    expect(afterExtraFailure?.total_retry_count).toBe(beforeExtraFailure?.total_retry_count)
    expect(afterExtraFailure?.next_retry_at).toBe(beforeExtraFailure?.next_retry_at)
    expect(afterExtraFailure?.last_error).toBe(beforeExtraFailure?.last_error)
  })

  it('uses capped retry delays', () => {
    expect(RETRY_DELAYS_SECONDS).toEqual([5, 10, 20, 40, 80, 160, 300, 300, 300, 300])
  })

  it('uses the stable pending upload storage key', () => {
    expect(PENDING_GAME_UPLOAD_KEY).toBe('motioncare.pendingGameUpload')
  })

  it('returns null for malformed pending cache values', () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, { payload: payload() })

    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('returns null for pending cache without raw detail', () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, {
      ...pending(),
      payload: {
        ...payload(),
        form_data: {
          accuracy_rate: 90,
          error_count: 1,
          difficulty: '中等',
        },
      },
    })

    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('returns null for pending cache with invalid retry numbers', () => {
    const storage = memoryStorage()
    const invalidValues = [Number.NaN, Number.POSITIVE_INFINITY, -1, 1.5]
    const numericFields: Array<keyof Pick<PendingGameUpload, 'retry_count' | 'total_retry_count' | 'next_retry_at' | 'created_at'>> = [
      'retry_count',
      'total_retry_count',
      'next_retry_at',
      'created_at',
    ]

    numericFields.forEach((field) => {
      invalidValues.forEach((value) => {
        storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, { ...pending(), [field]: value })
        expect(loadPendingGameUpload(storage)).toBeNull()
      })
    })
  })

  it('returns null for pending cache with non-boolean paused flag', () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, {
      ...pending(),
      retry_paused_until_next_launch: 'false',
    })

    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('returns null when storage read fails', () => {
    const storage = {
      getStorageSync: vi.fn(() => {
        throw new Error('bad cache')
      }),
      setStorageSync: vi.fn(),
      removeStorageSync: vi.fn(),
    }

    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('returns null when marking retry failure without a pending upload', () => {
    const storage = memoryStorage()

    expect(markRetryFailure(storage, '网络失败', 1000)).toBeNull()
  })

  it('returns null when resetting retry window without a pending upload', () => {
    const storage = memoryStorage()

    expect(resetRetryWindowForLaunch(storage)).toBeNull()
  })
})
