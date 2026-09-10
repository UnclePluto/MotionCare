import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({
  default: {
    getStorageSync: vi.fn(),
    removeStorageSync: vi.fn(),
    redirectTo: vi.fn(),
    request: vi.fn(),
  },
}))

import Taro from '@tarojs/taro'

import type { GameTrainingPayload } from './gameTypes'
import {
  PENDING_GAME_UPLOAD_KEY,
  type PendingGameUpload,
  RETRY_DELAYS_SECONDS,
  clearPendingGameUpload,
  loadPendingGameUpload,
  markRetryFailure,
  postGameTrainingRecord,
  resetRetryWindowForLaunch,
  savePendingGameUploadAfterActiveRetry,
  savePendingGameUpload,
  startPendingGameUploadRetryLoop,
  stopPendingGameUploadRetryLoop,
  subscribePendingGameUploadRetryLoop,
  tryUploadPendingGameRecord,
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

afterEach(() => {
  stopPendingGameUploadRetryLoop()
  vi.useRealTimers()
})

describe('pending game upload retry state', () => {
  it.each([false, true])('补传只改变三个传输字段，兼容旧缓存=%s', async legacy => {
    const original: GameTrainingPayload = payload()
    if (!legacy) {
      original.client_session_id = '00000000-0000-4000-8000-000000000001'
      original.question_results = [{question_index: 1, game_code: 'game-memory-color-sequence', difficulty: '中等', response_duration_ms: 2500, is_correct: true, result_type: 'answered', swap_count: null}]
    }
    const storage = memoryStorage()
    savePendingGameUpload(storage, original, 1000)
    markRetryFailure(storage, '断网', 1000)
    const uploader = vi.fn().mockResolvedValue(undefined)
    await expect(tryUploadPendingGameRecord(storage, 6000, uploader)).resolves.toBe('uploaded')
    expect(uploader.mock.calls[0][0]).toEqual({
      ...original,
      form_data: {...original.form_data, raw_detail: {...original.form_data.raw_detail, upload_mode: 'retry', retry_count: 1, total_retry_count: 1}},
    })
    expect(original.form_data.raw_detail.upload_mode).toBe('direct')
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('409身份冲突停止自动补传循环', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = memoryStorage()
    savePendingGameUpload(storage, payload(), 1000)
    vi.mocked(Taro.request).mockResolvedValueOnce({statusCode: 409, data: {detail: '会话载荷冲突'}} as never)
    const uploader = vi.fn(postGameTrainingRecord)
    startPendingGameUploadRetryLoop(storage, {uploader})
    await vi.advanceTimersByTimeAsync(1)
    await vi.advanceTimersByTimeAsync(1000000)
    expect(uploader).toHaveBeenCalledTimes(1)
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it.each([
    ['detail', 'Authorization: Bearer patient-token'],
    ['message', 'token=patient-token secret=server-secret access_key=key credential_id=id AK=ak SK=sk'],
  ] as const)('does not expose sensitive API %s errors', async (field, sensitiveMessage) => {
    vi.mocked(Taro.request).mockResolvedValueOnce({
      statusCode: 400,
      data: { [field]: sensitiveMessage },
    } as never)

    await expect(postGameTrainingRecord(payload())).rejects.toThrow('请求失败')
  })

  it('does not expose a sensitive network Error.message', async () => {
    vi.mocked(Taro.request).mockRejectedValueOnce(new Error('request:fail Authorization: Bearer patient-token'))

    await expect(postGameTrainingRecord(payload())).rejects.toThrow('网络异常，稍后自动补传')
  })

  it('neutralizes medical terms returned by the training upload API', async () => {
    vi.mocked(Taro.request).mockResolvedValueOnce({
      statusCode: 400,
      data: { detail: '患者处方已更新，请联系医护' },
    } as never)

    await expect(postGameTrainingRecord(payload())).rejects.toThrow('用户运动计划已更新，请联系指导老师')
  })

  it('stores one pending upload and clears it after success', () => {
    const storage = memoryStorage()

    savePendingGameUpload(storage, payload(), 1000)
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(100)

    clearPendingGameUpload(storage)
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('旧单对象缓存转为队列，追加不同记录且不覆盖旧数据', () => {
    const storage = memoryStorage()
    const firstPayload = payload()
    const secondPayload = { ...payload(), prescription_action: 200 }

    savePendingGameUpload(storage, firstPayload, 1000)
    const saved = savePendingGameUpload(storage, secondPayload, 2000)

    expect(saved.payload.prescription_action).toBe(200)
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(100)
    clearPendingGameUpload(storage, firstPayload)
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(200)
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

  it('returns none when there is no pending upload to retry', async () => {
    const storage = memoryStorage()
    const uploader = vi.fn()

    await expect(tryUploadPendingGameRecord(storage, 1000, uploader)).resolves.toBe('none')
    expect(uploader).not.toHaveBeenCalled()
  })

  it('returns waiting without uploading when the next retry time has not arrived', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 5000 }))
    const uploader = vi.fn()

    await expect(tryUploadPendingGameRecord(storage, 4000, uploader)).resolves.toBe('waiting')
    expect(uploader).not.toHaveBeenCalled()
  })

  it('returns waiting without uploading when the pending upload is paused until next launch', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(
      PENDING_GAME_UPLOAD_KEY,
      pending({ next_retry_at: 1000, retry_paused_until_next_launch: true })
    )
    const uploader = vi.fn()

    await expect(tryUploadPendingGameRecord(storage, 2000, uploader)).resolves.toBe('waiting')
    expect(uploader).not.toHaveBeenCalled()
  })

  it('uploads due pending data in retry mode and clears the pending upload after success', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(
      PENDING_GAME_UPLOAD_KEY,
      pending({
        retry_count: 3,
        total_retry_count: 8,
        next_retry_at: 1000,
      })
    )
    const uploader = vi.fn().mockResolvedValue(undefined)

    await expect(tryUploadPendingGameRecord(storage, 1000, uploader)).resolves.toBe('uploaded')

    expect(uploader).toHaveBeenCalledTimes(1)
    expect(uploader.mock.calls[0][0].form_data.raw_detail.upload_mode).toBe('retry')
    expect(uploader.mock.calls[0][0].form_data.raw_detail.retry_count).toBe(3)
    expect(uploader.mock.calls[0][0].form_data.raw_detail.total_retry_count).toBe(8)
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it.each(['', '今天状态不佳'])('补传保留困难档与原始原因：%s', async (reason) => {
    const storage = memoryStorage()
    const record = payload()
    record.form_data.difficulty = '困难'
    record.form_data.raw_detail.prescribed_difficulty = '简单'
    record.form_data.raw_detail.difficulty_adjusted = true
    record.form_data.raw_detail.difficulty_adjust_reason = reason
    savePendingGameUpload(storage, record, 1000)
    const uploader = vi.fn().mockResolvedValue(undefined)

    await expect(tryUploadPendingGameRecord(storage, 1_000_000, uploader)).resolves.toBe('uploaded')
    expect(uploader).toHaveBeenCalledWith(expect.objectContaining({
      form_data: expect.objectContaining({
        difficulty: '困难',
        raw_detail: expect.objectContaining({
          prescribed_difficulty: '简单', difficulty_adjusted: true, difficulty_adjust_reason: reason,
        }),
      }),
    }))
    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('marks retry failure and pauses after the tenth retry in the current launch window', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(
      PENDING_GAME_UPLOAD_KEY,
      pending({
        retry_count: 9,
        total_retry_count: 12,
        next_retry_at: 1000,
      })
    )
    const uploader = vi.fn().mockRejectedValue(Object.assign(new Error('服务器错误'), { retryable: true, statusCode: 500 }))

    await expect(tryUploadPendingGameRecord(storage, 1000, uploader)).resolves.toBe('failed')

    const pendingUpload = loadPendingGameUpload(storage)
    expect(pendingUpload?.retry_count).toBe(10)
    expect(pendingUpload?.total_retry_count).toBe(13)
    expect(pendingUpload?.last_error).toBe('服务器错误')
    expect(pendingUpload?.retry_paused_until_next_launch).toBe(true)
  })

  it('does not persist a sensitive retryable custom uploader error', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const uploader = vi.fn().mockRejectedValue(
      Object.assign(new Error('Authorization: Bearer patient-token'), { retryable: true, statusCode: 500 })
    )

    await expect(tryUploadPendingGameRecord(storage, 1000, uploader)).resolves.toBe('failed')

    expect(loadPendingGameUpload(storage)?.last_error).toBe('上传失败，稍后自动补传')
  })

  it('filters sensitive text at the last_error write boundary', () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending())

    markRetryFailure(storage, 'credential_id=id AK=ak SK=sk', 1000)

    expect(loadPendingGameUpload(storage)?.last_error).toBe('上传失败，稍后自动补传')
  })

  it('neutralizes safe medical text persisted from a custom uploader error', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const uploader = vi.fn().mockRejectedValue(
      Object.assign(new Error('患者处方已更新，请联系医护'), { retryable: true, statusCode: 500 })
    )

    await expect(tryUploadPendingGameRecord(storage, 1000, uploader)).resolves.toBe('failed')

    expect(loadPendingGameUpload(storage)?.last_error).toBe('用户运动计划已更新，请联系指导老师')
  })

  it('clears pending upload and returns rejected for non-retryable status errors', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const uploader = vi.fn().mockRejectedValue(Object.assign(new Error('参数错误'), { retryable: false, statusCode: 400 }))

    await expect(tryUploadPendingGameRecord(storage, 1000, uploader)).resolves.toBe('rejected')

    expect(loadPendingGameUpload(storage)).toBeNull()
  })

  it('schedules retry from the failure time instead of the request start time', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const uploader = vi.fn(
      () =>
        new Promise<void>((_resolve, reject) => {
          setTimeout(() => reject(Object.assign(new Error('服务器错误'), { retryable: true, statusCode: 500 })), 30000)
        })
    )

    const retry = tryUploadPendingGameRecord(storage, 1000, uploader)
    await vi.advanceTimersByTimeAsync(30000)

    await expect(retry).resolves.toBe('failed')
    expect(loadPendingGameUpload(storage)?.next_retry_at).toBe(36000)
  })

  it('saves a new payload after the active old pending retry succeeds', async () => {
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const nextPayload = { ...payload(), prescription_action: 200 }
    let resolveUpload: (() => void) | undefined
    const uploader = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveUpload = resolve
        })
    )

    const retry = tryUploadPendingGameRecord(storage, 1000, uploader)
    const saved = savePendingGameUploadAfterActiveRetry(storage, nextPayload, 2000)
    resolveUpload?.()
    await retry

    await expect(saved).resolves.toMatchObject({ payload: nextPayload })
    expect(loadPendingGameUpload(storage)?.payload.prescription_action).toBe(200)
  })

  it('continues retry loop at next_retry_at after the first retryable failure', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const uploader = vi
      .fn()
      .mockRejectedValueOnce(Object.assign(new Error('服务器错误'), { retryable: true, statusCode: 500 }))
      .mockResolvedValueOnce(undefined)

    startPendingGameUploadRetryLoop(storage, { uploader })
    await vi.runOnlyPendingTimersAsync()

    expect(uploader).toHaveBeenCalledTimes(1)
    expect(loadPendingGameUpload(storage)?.next_retry_at).toBe(6000)

    await vi.advanceTimersByTimeAsync(4999)
    expect(uploader).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1)
    expect(uploader).toHaveBeenCalledTimes(2)
    expect(loadPendingGameUpload(storage)).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('pauses after the tenth retry in the loop and does not schedule another retry in the same launch', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = memoryStorage()
    storage.setStorageSync(
      PENDING_GAME_UPLOAD_KEY,
      pending({
        retry_count: 9,
        total_retry_count: 20,
        next_retry_at: 1000,
      })
    )
    const uploader = vi.fn().mockRejectedValue(Object.assign(new Error('服务器错误'), { retryable: true, statusCode: 500 }))

    startPendingGameUploadRetryLoop(storage, { uploader })
    await vi.runOnlyPendingTimersAsync()

    const pendingUpload = loadPendingGameUpload(storage)
    expect(uploader).toHaveBeenCalledTimes(1)
    expect(pendingUpload?.retry_count).toBe(10)
    expect(pendingUpload?.retry_paused_until_next_launch).toBe(true)
    expect(vi.getTimerCount()).toBe(0)

    await vi.advanceTimersByTimeAsync(600000)
    expect(uploader).toHaveBeenCalledTimes(1)
  })

  it('clears pending upload and stops the retry loop after success', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = memoryStorage()
    storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const uploader = vi.fn().mockResolvedValue(undefined)

    startPendingGameUploadRetryLoop(storage, { uploader })
    await vi.runOnlyPendingTimersAsync()

    expect(uploader).toHaveBeenCalledTimes(1)
    expect(loadPendingGameUpload(storage)).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps the retry loop stable when a listener throws', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = memoryStorage()
    storage.setStorageSync(
      PENDING_GAME_UPLOAD_KEY,
      pending({
        retry_count: 0,
        total_retry_count: 0,
        next_retry_at: 1000,
      })
    )
    const uploader = vi
      .fn()
      .mockRejectedValueOnce(Object.assign(new Error('服务器错误'), { retryable: true, statusCode: 500 }))
      .mockResolvedValueOnce(undefined)
    const listener = vi.fn(() => {
      throw new Error('page refresh failed')
    })

    const unsubscribe = subscribePendingGameUploadRetryLoop(listener)
    startPendingGameUploadRetryLoop(storage, { uploader })
    await vi.runOnlyPendingTimersAsync()
    await vi.advanceTimersByTimeAsync(5000)

    expect(listener).toHaveBeenCalledWith('failed')
    expect(uploader).toHaveBeenCalledTimes(2)
    expect(loadPendingGameUpload(storage)).toBeNull()
    unsubscribe()
  })

  it('stops the retry loop when storage failure rejects the retry attempt', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    const storage = {
      getStorageSync: vi.fn(() => pending({ next_retry_at: 1000 })),
      setStorageSync: vi.fn(),
      removeStorageSync: vi.fn(() => {
        throw new Error('storage unavailable')
      }),
    }
    const uploader = vi.fn().mockResolvedValue(undefined)

    startPendingGameUploadRetryLoop(storage, { uploader })
    await vi.runOnlyPendingTimersAsync()

    expect(uploader).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)

    const healthyStorage = memoryStorage()
    healthyStorage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending({ next_retry_at: 1000 }))
    const secondUploader = vi.fn().mockResolvedValue(undefined)

    startPendingGameUploadRetryLoop(healthyStorage, { uploader: secondUploader })
    await vi.runOnlyPendingTimersAsync()

    expect(secondUploader).toHaveBeenCalledTimes(1)
  })
})

it('v2缓存与入参、读取结果及上传器的嵌套步骤互不污染', async () => {
  const storage = memoryStorage()
  const original = payload()
  original.client_session_id = '00000000-0000-4000-8000-000000000001'
  original.question_results = [{capture_version: 'active_response_v2', question_index: 1, game_code: 'game-memory-color-sequence', difficulty: '简单', response_duration_ms: 100, is_correct: false, result_type: 'interrupted', swap_count: null, click_count: null, expected_step_count: 3, selection_steps: [{step_index: 1, selected_value: 'blue', expected_value: 'green', response_duration_ms: 100, is_correct: false}]}]
  const saved = savePendingGameUpload(storage, original, 1000)
  original.question_results[0].selection_steps![0].selected_value = 'red'
  saved.payload.question_results![0].selection_steps![0].selected_value = 'yellow'
  loadPendingGameUpload(storage)!.payload.question_results![0].selection_steps![0].selected_value = 'teal'
  const uploader = vi.fn(async (uploaded: GameTrainingPayload) => {
    expect(uploaded.question_results![0].selection_steps![0].selected_value).toBe('blue')
    uploaded.question_results![0].selection_steps![0].selected_value = 'red'
    throw new Error('网络中断')
  })
  expect(await tryUploadPendingGameRecord(storage, 1000, uploader)).toBe('failed')
  expect(loadPendingGameUpload(storage)!.payload.question_results![0].selection_steps![0].selected_value).toBe('blue')
})

it('等待旧记录补传期间冻结新记录快照', async () => {
  const storage = memoryStorage()
  savePendingGameUpload(storage, payload(), 1000)
  let release!: () => void
  const active = tryUploadPendingGameRecord(storage, 1000, () => new Promise<void>(resolve => { release = resolve }))
  const next = payload()
  next.client_session_id = '00000000-0000-4000-8000-000000000002'
  const saving = savePendingGameUploadAfterActiveRetry(storage, next, 1000)
  next.form_data.raw_detail.completed_units = 999
  release()
  await active
  await saving
  expect(loadPendingGameUpload(storage)?.payload.form_data.raw_detail.completed_units).toBe(10)
})

it('已有旧UUID待补传时，新半题卸载保存后两条都能恢复', async () => {
  const storage = memoryStorage()
  const old = {...payload(), client_session_id: '00000000-0000-4000-8000-000000000001'}
  const fresh = {...payload(), client_session_id: '00000000-0000-4000-8000-000000000002', question_results: [{capture_version: 'active_response_v2' as const, question_index: 1, game_code: 'game-memory-color-sequence' as const, difficulty: '简单' as const, response_duration_ms: 100, is_correct: false, result_type: 'interrupted' as const, swap_count: null, click_count: null, expected_step_count: 3, selection_steps: [{step_index: 1, selected_value: 'blue', expected_value: 'green', response_duration_ms: 100, is_correct: false}]}]}
  savePendingGameUpload(storage, old, 1000)
  const saved = savePendingGameUpload(storage, fresh, 1000)
  expect(saved.payload.client_session_id).toBe(fresh.client_session_id)
  const uploader = vi.fn().mockResolvedValue(undefined)
  await tryUploadPendingGameRecord(storage, 1000, uploader)
  expect(loadPendingGameUpload(storage)?.payload).toEqual(fresh)
  await tryUploadPendingGameRecord(storage, 1000, uploader)
  expect(uploader.mock.calls.map(([p]) => p.client_session_id)).toEqual([old.client_session_id, fresh.client_session_id])
})

it.each(['成功', '失败'])('上传旧UUID期间追加新UUID，旧请求%s只操作旧项', async outcome => {
  const storage = memoryStorage()
  const old = {...payload(), client_session_id: 'old'}
  const fresh = {...payload(), client_session_id: 'new'}
  savePendingGameUpload(storage, old, 1000)
  let resolve!: () => void
  let reject!: (error: Error) => void
  const running = tryUploadPendingGameRecord(storage, 1000, () => new Promise<void>((ok, no) => { resolve = ok; reject = no }))
  const saved = await savePendingGameUploadAfterActiveRetry(storage, fresh, 1000)
  expect(saved.payload.client_session_id).toBe('new')
  fresh.form_data.raw_detail.completed_units = 999
  saved.payload.form_data.raw_detail.completed_units = 888
  if (outcome === '成功') resolve()
  else reject(new Error('断网'))
  await running
  if (outcome === '失败') {
    expect(loadPendingGameUpload(storage)).toMatchObject({retry_count: 1, payload: {client_session_id: 'old'}})
    clearPendingGameUpload(storage, old)
  }
  expect(loadPendingGameUpload(storage)).toMatchObject({retry_count: 0, payload: {client_session_id: 'new', form_data: {raw_detail: {completed_units: 10}}}})
})

it('重复保存UUID不改变原始内容，指定清理另一UUID不清除队首', () => {
  const storage = memoryStorage()
  const old = {...payload(), client_session_id: 'old'}
  const fresh = {...payload(), client_session_id: 'new'}
  savePendingGameUpload(storage, old, 1000)
  savePendingGameUpload(storage, fresh, 1000)
  savePendingGameUpload(storage, {...fresh, score: 0}, 2000)
  clearPendingGameUpload(storage, old)
  expect(loadPendingGameUpload(storage)?.payload.score).toBe(90)
  clearPendingGameUpload(storage, old)
  expect(loadPendingGameUpload(storage)?.payload.client_session_id).toBe('new')
})

it('队列循环连续补传两UUID并最终清空', async () => {
  vi.useFakeTimers(); vi.setSystemTime(1000)
  const storage = memoryStorage()
  savePendingGameUpload(storage, {...payload(), client_session_id: 'old'}, 1000)
  savePendingGameUpload(storage, {...payload(), client_session_id: 'new'}, 1000)
  const uploader = vi.fn().mockResolvedValue(undefined)
  startPendingGameUploadRetryLoop(storage, {uploader})
  await vi.advanceTimersByTimeAsync(10)
  expect(uploader.mock.calls.map(([p]) => p.client_session_id)).toEqual(['old', 'new'])
  expect(loadPendingGameUpload(storage)).toBeNull()
})

it.each([401, 403])('%s清理鉴权并停止循环，不上传或删除队列后续UUID', async status => {
  vi.useFakeTimers(); vi.setSystemTime(1000)
  const storage = memoryStorage()
  savePendingGameUpload(storage, {...payload(), client_session_id: 'old'}, 1000)
  savePendingGameUpload(storage, {...payload(), client_session_id: 'new'}, 1000)
  vi.mocked(Taro.request).mockClear().mockResolvedValueOnce({statusCode: status, data: {}} as never)
  vi.mocked(Taro.removeStorageSync).mockClear()
  vi.mocked(Taro.redirectTo).mockClear()
  startPendingGameUploadRetryLoop(storage)
  await vi.advanceTimersByTimeAsync(10000)
  expect(Taro.request).toHaveBeenCalledTimes(1)
  expect(Taro.removeStorageSync).toHaveBeenCalledWith('motioncare_patient_app_token')
  expect(Taro.redirectTo).toHaveBeenCalledWith({url: '/pages/bind/index'})
  expect(loadPendingGameUpload(storage)?.payload.client_session_id).toBe('new')
})

it.each([400, 409])('旧项%s业务拒绝通知后继续本轮上传有效新项', async status => {
  vi.useFakeTimers(); vi.setSystemTime(1000)
  const storage = memoryStorage()
  savePendingGameUpload(storage, {...payload(), client_session_id: 'old'}, 1000)
  savePendingGameUpload(storage, {...payload(), client_session_id: 'new'}, 1000)
  const uploader = vi.fn().mockRejectedValueOnce(Object.assign(new Error('业务拒绝'), {statusCode: status, retryable: false})).mockResolvedValueOnce(undefined)
  const listener = vi.fn()
  const unsubscribe = subscribePendingGameUploadRetryLoop(listener)
  try {
    startPendingGameUploadRetryLoop(storage, {uploader})
    await vi.advanceTimersByTimeAsync(10)
    expect(uploader.mock.calls.map(([p]) => p.client_session_id)).toEqual(['old', 'new'])
    expect(listener.mock.calls.map(([result]) => result)).toEqual(['rejected', 'uploaded'])
    expect(loadPendingGameUpload(storage)).toBeNull()
  } finally { unsubscribe() }
})

it('清理已成功队首时存储失败则停止循环且两项仍保留', async () => {
  vi.useFakeTimers(); vi.setSystemTime(1000)
  const storage = memoryStorage()
  savePendingGameUpload(storage, {...payload(), client_session_id: 'old'}, 1000)
  savePendingGameUpload(storage, {...payload(), client_session_id: 'new'}, 1000)
  storage.setStorageSync.mockImplementationOnce(() => { throw new Error('存储失败') })
  const uploader = vi.fn().mockResolvedValue(undefined)
  startPendingGameUploadRetryLoop(storage, {uploader})
  await vi.advanceTimersByTimeAsync(10000)
  expect(uploader).toHaveBeenCalledTimes(1)
  expect(loadPendingGameUpload(storage)?.payload.client_session_id).toBe('old')
  clearPendingGameUpload(storage)
  expect(loadPendingGameUpload(storage)?.payload.client_session_id).toBe('new')
})
