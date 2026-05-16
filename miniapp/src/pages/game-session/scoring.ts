import type { GameCode, GameDifficulty, GameEndReason, GameTrainingPayload, GameUploadMode, TrainingStatus } from './gameTypes'

type BuildGameTrainingResultInput = {
  gameCode: GameCode
  prescribedDifficulty: string
  actualDifficulty: GameDifficulty
  difficultyAdjustReason: string
  endedBy: GameEndReason
  durationSeconds: number
  suggestedDurationMinutes: number
  completedUnits: number
  correctUnits: number
  uploadMode: GameUploadMode
  retryCount: number
  totalRetryCount: number
}

export function minutesFromSeconds(seconds: number): number {
  if (!Number.isFinite(seconds) || seconds <= 0) return 0
  return Math.ceil(seconds / 60)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function nonNegativeInteger(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0
  return Math.round(value)
}

function expectedUnits(suggestedDurationMinutes: number): number {
  return Math.max(1, suggestedDurationMinutes * 2)
}

export function buildGameTrainingResult(
  input: BuildGameTrainingResultInput
): Omit<GameTrainingPayload, 'prescription_action' | 'training_date' | 'note'> {
  const durationSeconds = nonNegativeInteger(input.durationSeconds)
  const suggestedDurationMinutes = nonNegativeInteger(input.suggestedDurationMinutes)
  const completedUnits = nonNegativeInteger(input.completedUnits)
  const correctUnits = clamp(nonNegativeInteger(input.correctUnits), 0, completedUnits)
  const errorCount = Math.max(0, completedUnits - correctUnits)
  const accuracyRate = completedUnits === 0 ? 0 : Math.round((correctUnits / completedUnits) * 100)
  const volumeBonus = Math.min(10, (completedUnits / expectedUnits(suggestedDurationMinutes)) * 10)
  const earlyPenalty = input.endedBy === 'manual' ? 10 : 0
  const score = clamp(Math.round(accuracyRate * 0.9 + volumeBonus - earlyPenalty), 0, 100)
  const status: TrainingStatus = input.endedBy === 'manual' ? 'partial' : 'completed'

  return {
    status,
    actual_duration_minutes: minutesFromSeconds(durationSeconds),
    score,
    form_data: {
      accuracy_rate: accuracyRate,
      error_count: errorCount,
      difficulty: input.actualDifficulty,
      raw_detail: {
        game_code: input.gameCode,
        ended_by: input.endedBy,
        ended_early: input.endedBy === 'manual',
        prescribed_difficulty: input.prescribedDifficulty,
        difficulty_adjusted: input.actualDifficulty !== input.prescribedDifficulty,
        difficulty_adjust_reason: input.difficultyAdjustReason,
        upload_mode: input.uploadMode,
        retry_count: nonNegativeInteger(input.retryCount),
        total_retry_count: nonNegativeInteger(input.totalRetryCount),
        session_duration_seconds: durationSeconds,
        suggested_duration_minutes: suggestedDurationMinutes,
        completed_units: completedUnits,
        correct_units: correctUnits,
      },
    },
  }
}
