import { describe, expect, it } from "vitest";

import {
  wearableMeasurementQueryKey,
  type WearableMeasurementQueryIdentity,
} from "./measurementQueries";

const BASE_IDENTITY: WearableMeasurementQueryIdentity = {
  patientId: 201,
  projectPatientId: 9001,
  bindingId: 17,
  deviceId: 7,
  metricType: "heart_rate",
  bucket: "raw",
  start: "2026-06-25",
  end: "2026-07-24",
};

describe("wearableMeasurementQueryKey", () => {
  it("患者、项目绑定、设备、指标、bucket 或日期变化时均隔离缓存", () => {
    const identities: WearableMeasurementQueryIdentity[] = [
      BASE_IDENTITY,
      { ...BASE_IDENTITY, patientId: 202 },
      { ...BASE_IDENTITY, projectPatientId: 9002 },
      { ...BASE_IDENTITY, bindingId: 18 },
      { ...BASE_IDENTITY, deviceId: 8 },
      { ...BASE_IDENTITY, metricType: "blood_oxygen" },
      { ...BASE_IDENTITY, bucket: "15m" },
      { ...BASE_IDENTITY, start: "2026-06-26" },
      { ...BASE_IDENTITY, end: "2026-07-23" },
    ];

    const serializedKeys = identities.map((identity) =>
      JSON.stringify(wearableMeasurementQueryKey(identity)),
    );

    expect(new Set(serializedKeys).size).toBe(identities.length);
  });
});
