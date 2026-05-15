export type TrainingTrackingRange = "30d" | "7d" | "weekly";

export type TrainingTrackingPatientSummary = {
  patient_id: number;
  patient_name: string;
  patient_phone: string;
  project_count: number;
  latest_training_at: string | null;
  completed_count_30d: number;
};

export type TrainingTrackingPatientsResponse =
  | TrainingTrackingPatientSummary[]
  | {
      results: TrainingTrackingPatientSummary[];
    };

export type TrainingTrackingPatient = {
  id: number;
  name: string;
  phone: string;
  gender?: string | null;
  age?: number | null;
};

export type TrainingTrackingProjectOption = {
  project_patient_id?: number;
  id?: number;
  project_id?: number;
  project?: number;
  project_name: string;
  group_name?: string | null;
  prescription_version?: number | null;
};

export type TrainingTrackingCurrentProjectPatient = {
  id?: number;
  project_patient_id?: number;
  project_id?: number;
  project?: number;
  project_name: string;
  group_name?: string | null;
  prescription_version?: number | null;
};

export type TrainingTrackingCurrentPrescription = {
  id: number;
  version: number;
  status?: string | null;
};

export type PrescriptionCompletionRow = {
  action_id: number;
  action_name: string;
  prescribed_count: number;
  completed_count: number;
  completion_rate: number;
};

export type TrainingTrendPoint = {
  date?: string;
  week_start?: string;
  label?: string;
  completed_count: number;
  moving_average?: number | null;
};

export type GamePerformanceRow = {
  game_name: string;
  completed_count: number;
  average_score: number | null;
  average_accuracy: number | null;
  total_errors: number;
};

export type GamePerformanceSummary = {
  average_score: number | null;
  average_accuracy: number | null;
  total_errors: number;
  by_game: GamePerformanceRow[];
};

export type RecentTrainingRecord = {
  id: number;
  trained_at: string | null;
  action_name: string;
  game_name?: string | null;
  status: string;
  score?: number | null;
  accuracy?: number | null;
  error_count?: number | null;
};

export type TrainingTrackingDetail = {
  patient: TrainingTrackingPatient;
  project_options: TrainingTrackingProjectOption[];
  projects?: TrainingTrackingProjectOption[];
  current_project_patient: TrainingTrackingCurrentProjectPatient | null;
  current_project?: TrainingTrackingCurrentProjectPatient | null;
  current_prescription: TrainingTrackingCurrentPrescription | null;
  prescription_completion: PrescriptionCompletionRow[];
  trends: {
    daily_30d: TrainingTrendPoint[];
    daily_7d: TrainingTrendPoint[];
    weekly: TrainingTrendPoint[];
  };
  game_summary: GamePerformanceSummary;
  recent_records: RecentTrainingRecord[];
};
