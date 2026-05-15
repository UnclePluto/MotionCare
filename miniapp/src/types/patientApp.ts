export type BoundIdentity = {
  project_patient_id: number
  patient: { id: number; name: string }
  project: { id: number; name: string }
}

export type TrainingRecordSummary = {
  id: number
  prescription: number
  prescription_action: number
  training_date: string
  status: 'completed' | 'partial' | 'missed'
  actual_duration_minutes: number | null
  score: string | null
  form_data: Record<string, unknown>
  note: string
}

export type CurrentPrescription = null | {
  id: number
  version: number
  status: string
  effective_at: string | null
  week_start: string
  week_end: string
  actions: Array<{
    id: number
    action_library_item: number
    action_name: string
    training_type: string
    internal_type: string
    action_type: string
    action_instruction: string
    video_url: string
    has_ai_supervision: boolean
    weekly_frequency: string
    duration_minutes: number | null
    weekly_target_count: number
    weekly_completed_count: number
    difficulty: string
    notes: string
    sort_order: number
    recent_record: TrainingRecordSummary | null
  }>
}

export type HomeData = BoundIdentity & {
  today: string
  has_daily_health_today: boolean
  current_prescription: CurrentPrescription
}

export type DailyHealth = {
  id: number
  record_date: string
  steps: number | null
  exercise_minutes: number | null
  average_heart_rate: number | null
  max_heart_rate: number | null
  min_heart_rate: number | null
  sleep_hours: string | null
  note: string
}
