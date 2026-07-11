export type TrainingTrackingRange = "30d" | "7d" | "weekly";

export type TrackingPatient = {
  id: number;
  name: string;
  phone_masked: string;
};

export type TrackingPatientRow = {
  patient: TrackingPatient;
  project_count: number;
  last_training_at: string | null;
  last_30_days_completed_count: number;
};

export type TrackingProjectPatient = {
  id: number;
  project: number;
  project_name: string;
  project_status: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string;
};

export type TrackingCurrentPrescription = {
  id: number;
  version: number;
  status: string;
  effective_at: string | null;
};

export type TrackingPrescriptionCompletionRow = {
  prescription_action: number;
  action_name: string;
  internal_type: string;
  action_type: string;
  target_count: number;
  completed_count: number;
  completion_rate: number;
  recent_record_at: string | null;
};

export type TrackingDailyTrendPoint = {
  date: string;
  completed_count: number;
  duration_minutes: number;
  game_average_score: number | null;
};

export type TrackingMovingAveragePoint = {
  date: string;
  completed_count_avg: number;
  duration_minutes_avg: number;
};

export type TrackingWeeklyTrendPoint = {
  week_start: string;
  week_end: string;
  completed_count: number;
  duration_minutes: number;
  game_average_score: number | null;
};

export type TrackingGameSummaryRow = {
  prescription_action: number;
  action_name: string;
  record_count: number;
  average_score: number | null;
  average_accuracy_rate: number | null;
  recent_record_at: string | null;
};

export type TrackingGameSummary = {
  average_score: number | null;
  average_accuracy_rate: number | null;
  total_error_count: number;
  by_game: TrackingGameSummaryRow[];
};

export type TrackingRecentRecord = {
  id: number;
  training_date: string;
  status: string;
  prescription: number;
  prescription_version: number;
  prescription_action: number;
  action_name: string;
  internal_type: string;
  action_type: string;
  actual_duration_minutes: number | null;
  score: number | null;
  game_accuracy_rate: number | null;
  game_error_count: number | null;
  game_difficulty: string | null;
  game_ended_early: boolean | null;
  game_difficulty_adjust_reason: string | null;
  game_upload_mode: string | null;
  game_retry_count: number | null;
  game_total_retry_count: number | null;
  note: string;
  video_id: number | null;
  video_status: string | null;
  latest_analysis_status: "pending" | "running" | "succeeded" | "failed" | null;
  analysis_total_count: number | null;
  analysis_standard_count: number | null;
  analysis_nonstandard_count: number | null;
};

export type TrackingPendingVideo = {
  id: number;
  training_date: string;
  action_name: string;
  status: "queued" | "assembling" | "uploading_qiniu" | "failed";
  failure_reason: string;
  created_at: string;
};

export type TrackingDetail = {
  patient: TrackingPatient;
  project_patients: TrackingProjectPatient[];
  selected_project_patient: TrackingProjectPatient | null;
  current_prescription: TrackingCurrentPrescription | null;
  prescription_completion: TrackingPrescriptionCompletionRow[];
  trend: {
    daily: TrackingDailyTrendPoint[];
    moving_average: TrackingMovingAveragePoint[];
    weekly: TrackingWeeklyTrendPoint[];
  };
  game_summary: TrackingGameSummary;
  recent_records: TrackingRecentRecord[];
  pending_training_videos: TrackingPendingVideo[];
};
