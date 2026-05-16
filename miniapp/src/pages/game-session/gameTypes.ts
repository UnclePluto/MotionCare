export type GameDifficulty = '简单' | '中等' | '困难'
export type GameCode = 'game-memory-color-sequence' | 'game-executive-inhibition'
export type GameEndReason = 'timer' | 'manual'
export type GameUploadMode = 'direct' | 'retry'
export type TrainingStatus = 'completed' | 'partial' | 'missed'

export const GAME_DIFFICULTIES: GameDifficulty[] = ['简单', '中等', '困难']

export type GameTrainingPayload = {
  prescription_action: number
  training_date: string
  status: TrainingStatus
  actual_duration_minutes: number
  score: number
  form_data: {
    accuracy_rate: number
    error_count: number
    difficulty: GameDifficulty
    raw_detail: {
      game_code: GameCode
      ended_by: GameEndReason
      ended_early: boolean
      prescribed_difficulty: string
      difficulty_adjusted: boolean
      difficulty_adjust_reason: string
      upload_mode: GameUploadMode
      retry_count: number
      total_retry_count: number
      session_duration_seconds: number
      suggested_duration_minutes: number
      completed_units: number
      correct_units: number
    }
  }
  note: string
}

export type GameActionSummary = {
  id: number
  action_name: string
  action_type: string
  action_instruction: string
  duration_minutes: number | null
  weekly_target_count: number
  weekly_completed_count: number
  difficulty: string
  notes: string
}
