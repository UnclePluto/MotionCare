export type ActionParameterMode = "duration" | "count";

export type ActionLibraryItem = {
  id: number;
  source_key: string | null;
  name: string;
  training_type: string;
  internal_type: "video" | "game" | "motion";
  action_type: string;
  instruction_text: string;
  suggested_frequency: string;
  suggested_duration_minutes: number | null;
  suggested_sets: number | null;
  suggested_repetitions: number | null;
  default_difficulty: string;
  video_url: string;
  has_ai_supervision: boolean;
  is_active: boolean;
  parameter_mode?: ActionParameterMode;
};

export type PrescriptionAction = {
  id: number;
  prescription: number;
  action_library_item: number;
  action_name_snapshot: string;
  training_type_snapshot: string;
  internal_type_snapshot: string;
  action_type_snapshot: string;
  action_instruction_snapshot: string;
  video_url_snapshot: string;
  has_ai_supervision_snapshot: boolean;
  weekly_frequency: string;
  duration_minutes: number | null;
  sets: number | null;
  repetitions: number | null;
  difficulty: string;
  notes: string;
  sort_order: number;
};

export type Prescription = {
  id: number;
  project_patient: number;
  version: number;
  opened_by: number;
  opened_by_name: string;
  opened_at: string;
  effective_at: string | null;
  status: "draft" | "active" | "pending" | "archived" | "terminated";
  note: string;
  actions: PrescriptionAction[];
};

export type ActivateNowActionPayload = {
  action_library_item: number;
  weekly_frequency?: string;
  duration_minutes?: number | null;
  sets?: number | null;
  repetitions?: number | null;
  difficulty?: string;
  notes?: string;
  sort_order?: number;
};
