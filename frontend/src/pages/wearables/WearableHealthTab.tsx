import { ReloadOutlined, WifiOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, DatePicker, Descriptions, Empty, Select, Space, Spin, Table, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { WearableMetricChart } from "./WearableMetricChart";
import type {
  PatientWearableSyncStatus,
  WearableBucket,
  WearableDailySummaryResponse,
  WearableMeasurementResponse,
  WearableMetricType,
} from "./types";

const METRIC_OPTIONS: Array<{ value: WearableMetricType; label: string }> = [
  { value: "heart_rate", label: "心率" },
  { value: "blood_pressure", label: "血压" },
  { value: "blood_oxygen", label: "血氧" },
  { value: "steps", label: "步数" },
];
const BUCKET_OPTIONS: Array<{ value: WearableBucket; label: string }> = [
  { value: "raw", label: "原始" },
  { value: "5m", label: "5 分钟" },
  { value: "15m", label: "15 分钟" },
  { value: "30m", label: "30 分钟" },
  { value: "1h", label: "1 小时" },
];

function rangeDefaults(): [Dayjs, Dayjs] {
  return [dayjs().subtract(29, "day"), dayjs()];
}

function errorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return fallback;
}

export function WearableHealthTab({ patientId, projectPatientId }: { patientId: number; projectPatientId: number }) {
  const [metricType, setMetricType] = useState<WearableMetricType>("heart_rate");
  const [bucket, setBucket] = useState<WearableBucket>("raw");
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(rangeDefaults);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const scopeRef = useRef(0);
  const scopeKey = `${patientId}:${projectPatientId}:${metricType}`;
  const currentScopeKey = useRef(scopeKey);
  if (currentScopeKey.current !== scopeKey) {
    currentScopeKey.current = scopeKey;
    scopeRef.current += 1;
  }

  useEffect(() => {
    scopeRef.current += 1;
    setFeedback(null);
    setPendingAction(null);
  }, [scopeKey]);

  const params = useMemo(
    () => ({
      project_patient: projectPatientId,
      start: dateRange[0].format("YYYY-MM-DD"),
      end: dateRange[1].format("YYYY-MM-DD"),
    }),
    [dateRange, projectPatientId],
  );
  const syncQuery = useQuery({
    queryKey: ["wearable-sync-status", patientId],
    queryFn: async () => (await apiClient.get<PatientWearableSyncStatus>(`/wearables/patients/${patientId}/sync-status/`)).data,
  });
  const isBound = syncQuery.data?.is_bound === true;
  const deviceIdRef = useRef<number | null>(syncQuery.data?.device_id ?? null);
  deviceIdRef.current = syncQuery.data?.device_id ?? null;
  const measurementsQuery = useQuery({
    queryKey: ["wearable-measurements", patientId, projectPatientId, metricType, bucket, params],
    enabled: isBound && metricType !== "steps",
    queryFn: async () =>
      (await apiClient.get<WearableMeasurementResponse>(`/wearables/patients/${patientId}/measurements/`, {
        params: { ...params, metric_type: metricType, bucket },
      })).data,
  });
  const dailyQuery = useQuery({
    queryKey: ["wearable-daily-summaries", patientId, projectPatientId, params],
    enabled: isBound,
    queryFn: async () =>
      (await apiClient.get<WearableDailySummaryResponse>(`/wearables/patients/${patientId}/daily-summaries/`, { params })).data,
  });

  const measurementCapability = metricType === "steps" ? false : syncQuery.data?.capabilities?.[`measure_${metricType}`] === true;
  const runAction = async (action: "status" | "measure" | "sync") => {
    const generation = scopeRef.current;
    const deviceId = syncQuery.data?.device_id;
    if (!isBound || (action === "status" && !deviceId)) return;
    setPendingAction(action);
    setFeedback(null);
    try {
      if (action === "status") await apiClient.post(`/wearables/devices/${deviceId}/check-status/`);
      if (action === "measure") await apiClient.post(`/wearables/patients/${patientId}/measure/`, { metric_type: metricType });
      if (action === "sync") await apiClient.post(`/wearables/patients/${patientId}/sync/`, { metric_type: metricType });
      if (scopeRef.current === generation && deviceIdRef.current === deviceId) {
        setFeedback({ type: "success", message: action === "status" ? "设备通信测试已完成。" : action === "measure" ? "主动测量请求已提交。" : "健康数据同步已提交。" });
      }
    } catch (error) {
      if (scopeRef.current === generation && deviceIdRef.current === deviceId) {
        setFeedback({ type: "error", message: errorMessage(error, "设备操作失败，请稍后重试。") });
      }
    } finally {
      if (scopeRef.current === generation && deviceIdRef.current === deviceId) setPendingAction(null);
    }
  };

  if (syncQuery.isLoading) return <Spin />;
  if (syncQuery.isError) return <Alert type="error" showIcon message={errorMessage(syncQuery.error, "加载穿戴健康摘要失败")} />;
  const syncStatus = syncQuery.data;
  if (!syncStatus?.is_bound) return <Empty description="请先在患者接入中绑定穿戴设备。" />;

  const metricName = METRIC_OPTIONS.find((option) => option.value === metricType)?.label;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Descriptions
        size="small"
        column={{ xs: 1, sm: 2, lg: 4 }}
        items={[
          { key: "device", label: "绑定设备", children: `设备 ${syncStatus.device_short_code ?? "—"}` },
          { key: "model", label: "设备型号", children: syncStatus.model ?? "—" },
          { key: "sync", label: "最近健康同步", children: syncStatus.last_sync_at ? dayjs(syncStatus.last_sync_at).format("YYYY-MM-DD HH:mm") : "—" },
          { key: "status", label: "指标", children: metricName },
        ]}
      />
      <Space wrap>
        <DatePicker.RangePicker aria-label="健康日期范围" value={dateRange} onChange={(value) => value?.[0] && value?.[1] && setDateRange([value[0], value[1]])} />
        <Select aria-label="健康指标" value={metricType} options={METRIC_OPTIONS} onChange={setMetricType} style={{ width: 120 }} />
        {metricType !== "steps" ? <Select aria-label="图表间隔" value={bucket} options={BUCKET_OPTIONS} onChange={setBucket} style={{ width: 120 }} /> : null}
        <Button icon={<WifiOutlined />} loading={pendingAction === "status"} onClick={() => void runAction("status")}>通信测试</Button>
        {metricType !== "steps" ? <Button disabled={!measurementCapability} loading={pendingAction === "measure"} onClick={() => void runAction("measure")}>主动测量</Button> : null}
        <Button icon={<ReloadOutlined />} loading={pendingAction === "sync"} onClick={() => void runAction("sync")}>主动同步</Button>
      </Space>
      {metricType !== "steps" && !measurementCapability ? <Alert type="info" showIcon message="该型号能力尚未验证" /> : null}
      {feedback ? <Alert type={feedback.type} showIcon message={feedback.message} /> : null}
      {metricType === "steps" ? (
        <Typography.Text>步数仅按日汇总展示，不提供日内趋势。</Typography.Text>
      ) : measurementsQuery.isError ? (
        <Alert type="error" showIcon message={errorMessage(measurementsQuery.error, "加载健康趋势失败")} />
      ) : (
        <WearableMetricChart metricType={metricType} data={measurementsQuery.data} />
      )}
      <Typography.Title level={5} style={{ margin: 0 }}>日汇总</Typography.Title>
      <Table
        rowKey="record_date"
        loading={dailyQuery.isLoading}
        dataSource={dailyQuery.data?.items ?? []}
        pagination={false}
        scroll={{ x: 760 }}
        columns={[
          { title: "日期", dataIndex: "record_date" },
          { title: "心率均值", dataIndex: "heart_rate_avg", render: (value: number | null | undefined) => value ?? "—" },
          { title: "血压均值", render: (_: unknown, row) => row.systolic_avg != null ? `${row.systolic_avg}/${row.diastolic_avg ?? "—"}` : "—" },
          { title: "血氧均值", dataIndex: "blood_oxygen_avg", render: (value: number | null | undefined) => value ?? "—" },
          { title: "步数", dataIndex: "steps", render: (value: number | null | undefined) => value ?? "—" },
        ]}
      />
    </Space>
  );
}
