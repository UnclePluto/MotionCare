import { apiClient } from "../../api/client";
import type {
  WearableBucket,
  WearableMeasurementResponse,
  WearableMetricType,
  WearableRawMeasurementResponse,
} from "./types";

type MeasurementQueryParams = {
  project_patient: number;
  metric_type: Exclude<WearableMetricType, "steps">;
  start: string;
  end: string;
  bucket: WearableBucket;
};

export type WearableMeasurementQueryIdentity = {
  patientId: number;
  projectPatientId: number;
  bindingId: number;
  deviceId: number;
  metricType: Exclude<WearableMetricType, "steps">;
  start: string;
  end: string;
  bucket: WearableBucket;
};

export function wearableMeasurementQueryKey(
  identity: WearableMeasurementQueryIdentity,
) {
  return [
    "wearable-measurements",
    identity.patientId,
    identity.projectPatientId,
    identity.bindingId,
    identity.deviceId,
    identity.metricType,
    identity.bucket,
    identity.start,
    identity.end,
  ] as const;
}

export function fetchWearableMeasurementsByIdentity({
  identity,
  signal,
}: {
  identity: WearableMeasurementQueryIdentity;
  signal?: AbortSignal;
}) {
  return fetchWearableMeasurements({
    patientId: identity.patientId,
    params: {
      project_patient: identity.projectPatientId,
      metric_type: identity.metricType,
      start: identity.start,
      end: identity.end,
      bucket: identity.bucket,
    },
    signal,
  });
}

export async function fetchWearableMeasurements({
  patientId,
  params,
  signal,
}: {
  patientId: number;
  params: MeasurementQueryParams;
  signal?: AbortSignal;
}): Promise<WearableMeasurementResponse> {
  const path = `/wearables/patients/${patientId}/measurements/`;
  if (params.bucket !== "raw") {
    return (
      await apiClient.get<WearableMeasurementResponse>(path, {
        params,
        signal,
      })
    ).data;
  }

  const items: WearableRawMeasurementResponse["items"] = [];
  const seenPages = new Set<number>();
  let page = 1;
  let firstResponse: WearableRawMeasurementResponse | null = null;

  while (true) {
    if (seenPages.has(page)) {
      throw new Error("原始趋势分页游标重复，已停止加载。");
    }
    seenPages.add(page);
    const response = (
      await apiClient.get<WearableRawMeasurementResponse>(path, {
        params: { ...params, page, page_size: 500 },
        signal,
      })
    ).data;
    firstResponse ??= response;
    items.push(...response.items);
    if (response.next_page == null) break;
    page = response.next_page;
  }

  items.sort((left, right) =>
    String(left.measured_at ?? "").localeCompare(
      String(right.measured_at ?? ""),
    ),
  );
  return {
    ...firstResponse!,
    page: 1,
    page_size: 500,
    next_page: null,
    items,
  };
}
