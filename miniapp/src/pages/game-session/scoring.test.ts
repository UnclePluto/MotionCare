import { describe, expect, it } from 'vitest'

import { buildGameTrainingResult, minutesFromSeconds } from './scoring'

describe('minutesFromSeconds', () => {
  it('rounds positive seconds up to integer minutes', () => {
    expect(minutesFromSeconds(1)).toBe(1)
    expect(minutesFromSeconds(60)).toBe(1)
    expect(minutesFromSeconds(61)).toBe(2)
  })

  it('returns zero when duration is zero', () => {
    expect(minutesFromSeconds(0)).toBe(0)
  })

  it('returns zero for non-finite duration values', () => {
    expect(minutesFromSeconds(Number.NaN)).toBe(0)
    expect(minutesFromSeconds(Number.POSITIVE_INFINITY)).toBe(0)
  })
})

describe('buildGameTrainingResult', () => {
  it('builds completed result for timer ended session', () => {
    const result = buildGameTrainingResult({
      gameCode: 'game-memory-color-sequence',
      prescribedDifficulty: '简单',
      actualDifficulty: '中等',
      difficultyAdjustReason: '太简单，想提高难度',
      endedBy: 'timer',
      durationSeconds: 600,
      suggestedDurationMinutes: 10,
      completedUnits: 10,
      correctUnits: 8,
      uploadMode: 'direct',
      retryCount: 0,
      totalRetryCount: 0,
    })

    expect(result.status).toBe('completed')
    expect(result.actual_duration_minutes).toBe(10)
    expect(result.score).toBe(77)
    expect(result.form_data.accuracy_rate).toBe(80)
    expect(result.form_data.error_count).toBe(2)
    expect(result.form_data.difficulty).toBe('中等')
    expect(result.form_data.raw_detail.ended_early).toBe(false)
    expect(result.form_data.raw_detail.difficulty_adjusted).toBe(true)
  })

  it('builds partial result for manual ended session', () => {
    const result = buildGameTrainingResult({
      gameCode: 'game-executive-inhibition',
      prescribedDifficulty: '困难',
      actualDifficulty: '困难',
      difficultyAdjustReason: '',
      endedBy: 'manual',
      durationSeconds: 130,
      suggestedDurationMinutes: 10,
      completedUnits: 5,
      correctUnits: 5,
      uploadMode: 'retry',
      retryCount: 3,
      totalRetryCount: 13,
    })

    expect(result.status).toBe('partial')
    expect(result.actual_duration_minutes).toBe(3)
    expect(result.score).toBe(83)
    expect(result.form_data.raw_detail.upload_mode).toBe('retry')
    expect(result.form_data.raw_detail.retry_count).toBe(3)
    expect(result.form_data.raw_detail.total_retry_count).toBe(13)
  })

  it('normalizes non-finite numeric input to finite result fields', () => {
    const result = buildGameTrainingResult({
      gameCode: 'game-memory-color-sequence',
      prescribedDifficulty: '简单',
      actualDifficulty: '简单',
      difficultyAdjustReason: '',
      endedBy: 'timer',
      durationSeconds: Number.POSITIVE_INFINITY,
      suggestedDurationMinutes: Number.NaN,
      completedUnits: Number.NaN,
      correctUnits: Number.POSITIVE_INFINITY,
      uploadMode: 'direct',
      retryCount: Number.NaN,
      totalRetryCount: Number.POSITIVE_INFINITY,
    })

    expect(Number.isInteger(result.score)).toBe(true)
    expect(result.score).toBeGreaterThanOrEqual(0)
    expect(result.score).toBeLessThanOrEqual(100)
    expect(result.actual_duration_minutes).toBe(0)
    expect(result.form_data.raw_detail.session_duration_seconds).toBe(0)
    expect(result.form_data.raw_detail.suggested_duration_minutes).toBe(0)
    expect(result.form_data.raw_detail.completed_units).toBe(0)
    expect(result.form_data.raw_detail.correct_units).toBe(0)

    const numericValues = [
      result.actual_duration_minutes,
      result.score,
      result.form_data.accuracy_rate,
      result.form_data.error_count,
      result.form_data.raw_detail.retry_count,
      result.form_data.raw_detail.total_retry_count,
      result.form_data.raw_detail.session_duration_seconds,
      result.form_data.raw_detail.suggested_duration_minutes,
      result.form_data.raw_detail.completed_units,
      result.form_data.raw_detail.correct_units,
    ]

    expect(numericValues.every((value) => Number.isFinite(value) && Number.isInteger(value) && value >= 0)).toBe(true)
  })
})
