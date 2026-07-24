export type WearableDevice = {
  id: number;
  provider: string;
  external_device_id: string;
  identifier_type: string;
  model: string;
  short_code: string;
  enabled: boolean;
  last_communication_at: string | null;
  last_status_checked_at?: string | null;
  last_sync_at?: string | null;
  current_patient_name?: string | null;
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
  online: boolean;
  battery_level: number | null;
  last_communication_at: string | null;
  capabilities?: {
    ring?: boolean;
  };
};
