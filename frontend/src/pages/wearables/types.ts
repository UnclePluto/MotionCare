export type WearableDevice = {
  id: number;
  provider: string;
  external_device_id: string;
  identifier_type: string;
  model: string;
  short_code: string;
  enabled: boolean;
  is_bound: boolean;
  current_patient_name: string | null;
  last_communication_at: string | null;
  last_status_checked_at: string | null;
  last_sync_at: string | null;
};

export type WearableBinding = {
  id: number;
  patient_id: number;
  device_id: number;
  short_code: string;
  bound_at: string;
  unbound_at?: string | null;
};

export type ProjectPatientWearableBinding = {
  project_patient_id: number;
  patient_id: number;
  binding: WearableBinding | null;
};

export type WearableStatus = {
  device_id: number;
  model: string;
  online: boolean;
  battery_level: number | null;
  last_communication_at: string | null;
  capabilities: {
    ring: boolean;
  };
};

export type WearableCommandCapabilities = {
  ring: boolean;
  measure_heart_rate: boolean;
  measure_blood_pressure: boolean;
  measure_blood_oxygen: boolean;
  configure_heart_rate_interval: boolean;
  configure_blood_pressure_interval: boolean;
  configure_blood_oxygen_interval: boolean;
  configure_step_switch: boolean;
};

export type PatientWearableSyncStatus = {
  is_bound: boolean;
  binding_id: number | null;
  device_id: number | null;
  model: string | null;
  device_short_code: string | null;
  last_device_status: string | null;
  last_battery_level: number | null;
  last_communication_at: string | null;
  capabilities: WearableCommandCapabilities;
  last_sync_at: string | null;
  metrics: Array<{ metric_type: string; status: string | null; last_success_at: string | null }>;
};

export type WearableMetricType = "heart_rate" | "blood_pressure" | "blood_oxygen" | "steps";
export type WearableBucket = "raw" | "5m" | "15m" | "30m" | "1h";

export type WearableMeasurementItem = Record<string, string | number | null>;

type WearableMeasurementResponseBase = {
  metric_type: Exclude<WearableMetricType, "steps">;
  start: string;
  end: string;
  items: WearableMeasurementItem[];
};

export type WearableRawMeasurementResponse = WearableMeasurementResponseBase & {
  bucket: "raw";
  total: number;
  page: number;
  page_size: number;
  next_page: number | null;
};

export type WearableBucketMeasurementResponse = WearableMeasurementResponseBase & {
  bucket: Exclude<WearableBucket, "raw">;
};

export type WearableMeasurementResponse =
  | WearableRawMeasurementResponse
  | WearableBucketMeasurementResponse;

export type WearableDailySummary = {
  record_date: string;
  heart_rate_avg?: number | null;
  heart_rate_min?: number | null;
  heart_rate_max?: number | null;
  heart_rate_count?: number;
  systolic_avg?: number | null;
  diastolic_avg?: number | null;
  blood_pressure_count?: number;
  blood_oxygen_avg?: number | null;
  blood_oxygen_min?: number | null;
  blood_oxygen_max?: number | null;
  blood_oxygen_count?: number;
  steps?: number | null;
  steps_attribution_status?: string;
  heart_rate_sync_status?: string;
  blood_pressure_sync_status?: string;
  blood_oxygen_sync_status?: string;
  steps_sync_status?: string;
};

export type WearableDailySummaryResponse = { items: WearableDailySummary[] };

export type WearableCommandStatus =
  | "succeeded"
  | "queued"
  | "offline"
  | "timeout"
  | "failed";

export type WearableCommandResponse = {
  id: number;
  command_type: string;
  status: WearableCommandStatus;
  provider_code: string;
  completed_at: string | null;
};

export type WearableSyncCommandResponse = {
  metric_types: WearableMetricType[];
  status: "queued";
};
