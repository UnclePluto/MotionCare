import { ReloadOutlined, WifiOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  DatePicker,
  Descriptions,
  Empty,
  InputNumber,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from "antd";
import { type Dayjs } from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import {
  clampHealthDateRange,
  formatShanghaiDateTime,
  isOutsideHealthRange,
  shanghaiToday,
} from "../../utils/shanghaiTime";
import {
  WearableMetricChart,
  WearableStepsChart,
} from "./WearableMetricChart";
import {
  fetchWearableMeasurementsByIdentity,
  wearableMeasurementQueryKey,
  type WearableMeasurementQueryIdentity,
} from "./measurementQueries";
import type {
  PatientWearableSyncStatus,
  WearableBucket,
  WearableCommandResponse,
  WearableDailySummary,
  WearableDailySummaryResponse,
  WearableMetricType,
  WearableStatus,
  WearableSyncCommandResponse,
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
  const today = shanghaiToday();
  return [today.subtract(29, "day"), today];
}

function errorDetails(value: unknown): string[] {
  if (typeof value === "string" && value.trim()) return [value.trim()];
  if (Array.isArray(value)) return value.flatMap(errorDetails);
  if (value && typeof value === "object") {
    return Object.values(value as Record<string, unknown>).flatMap(errorDetails);
  }
  return [];
}

function errorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const data = (error as { response?: { data?: unknown } }).response?.data;
    const messages = errorDetails(data);
    if (messages.length > 0) return [...new Set(messages)].join("；");
  }
  return fallback;
}

const SYNC_STATUS_LABEL: Record<string, string> = {
  pending: "待同步",
  succeeded: "同步成功",
  failed: "同步失败",
};

const ATTRIBUTION_STATUS_LABEL: Record<string, string> = {
  attributed: "已归属",
  outside_binding: "绑定区间外",
  ambiguous: "归属不明确",
};

function statusText(value: string | null | undefined, labels: Record<string, string>) {
  if (!value) return "—";
  const label = labels[value] ?? value;
  const color =
    value === "succeeded" || value === "attributed"
      ? "success"
      : value === "failed" || value === "ambiguous"
        ? "error"
        : "warning";
  return <Tag color={color}>{label}</Tag>;
}

function dailyColumns(
  metricType: WearableMetricType,
): TableColumnsType<WearableDailySummary> {
  const dateColumn = { title: "日期", dataIndex: "record_date" };
  if (metricType === "heart_rate") {
    return [
      dateColumn,
      { title: "心率均值", dataIndex: "heart_rate_avg", render: valueOrDash },
      { title: "最低心率", dataIndex: "heart_rate_min", render: valueOrDash },
      { title: "最高心率", dataIndex: "heart_rate_max", render: valueOrDash },
      { title: "测量次数", dataIndex: "heart_rate_count", render: valueOrDash },
      {
        title: "同步状态",
        dataIndex: "heart_rate_sync_status",
        render: (value) => statusText(value, SYNC_STATUS_LABEL),
      },
    ];
  }
  if (metricType === "blood_pressure") {
    return [
      dateColumn,
      { title: "收缩压均值", dataIndex: "systolic_avg", render: valueOrDash },
      { title: "舒张压均值", dataIndex: "diastolic_avg", render: valueOrDash },
      { title: "测量次数", dataIndex: "blood_pressure_count", render: valueOrDash },
      {
        title: "同步状态",
        dataIndex: "blood_pressure_sync_status",
        render: (value) => statusText(value, SYNC_STATUS_LABEL),
      },
    ];
  }
  if (metricType === "blood_oxygen") {
    return [
      dateColumn,
      { title: "血氧均值", dataIndex: "blood_oxygen_avg", render: valueOrDash },
      { title: "最低血氧", dataIndex: "blood_oxygen_min", render: valueOrDash },
      { title: "最高血氧", dataIndex: "blood_oxygen_max", render: valueOrDash },
      { title: "测量次数", dataIndex: "blood_oxygen_count", render: valueOrDash },
      {
        title: "同步状态",
        dataIndex: "blood_oxygen_sync_status",
        render: (value) => statusText(value, SYNC_STATUS_LABEL),
      },
    ];
  }
  return [
    dateColumn,
    { title: "步数", dataIndex: "steps", render: valueOrDash },
    {
      title: "归属状态",
      dataIndex: "steps_attribution_status",
      render: (value) => statusText(value, ATTRIBUTION_STATUS_LABEL),
    },
    {
      title: "同步状态",
      dataIndex: "steps_sync_status",
      render: (value) => statusText(value, SYNC_STATUS_LABEL),
    },
  ];
}

function valueOrDash(value: number | null | undefined) {
  return value ?? "—";
}

function LoadingState({ label }: { label: string }) {
  return (
    <Space>
      <Spin size="small" />
      <Typography.Text>{label}</Typography.Text>
    </Space>
  );
}

type Feedback = {
  type: "success" | "info" | "warning" | "error";
  message: string;
  description?: string;
};

type ActionRequest = {
  id: number;
  scopeKey: string;
  patientId: number;
  projectPatientId: number;
  metricType: WearableMetricType;
  deviceId: number;
  bindingId: number;
  measurementIdentity: WearableMeasurementQueryIdentity | null;
};

type ScopedFeedback = {
  scopeKey: string;
  value: Feedback;
};

type ScopedDeviceStatus = {
  scopeKey: string;
  value: WearableStatus;
};

type PendingOperation = {
  scopeKey: string;
  action: string;
};

type DeviceDraftState = {
  deviceIdentity: string;
  heartRateInterval: number | null;
  bloodPressureInterval: number | null;
  bloodOxygenInterval: number | null;
  stepEnabled: boolean;
};

const DEFAULT_DEVICE_DRAFTS = {
  heartRateInterval: 60,
  bloodPressureInterval: 60,
  bloodOxygenInterval: 60,
  stepEnabled: true,
} as const;

const MEASUREMENT_POLL_ATTEMPTS = 6;
const MEASUREMENT_POLL_INTERVAL_MS = 10_000;

function waitForPollInterval() {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, MEASUREMENT_POLL_INTERVAL_MS);
  });
}

function measurementSignature(data: { items: unknown[] } | undefined) {
  return JSON.stringify(data?.items ?? []);
}

function commandFeedback(
  status: WearableCommandResponse["status"],
  actionLabel: string,
): Feedback {
  if (status === "succeeded") {
    return { type: "success", message: `${actionLabel}命令已成功。` };
  }
  if (status === "queued") {
    return { type: "info", message: `${actionLabel}命令已排队。` };
  }
  if (status === "offline") {
    return { type: "warning", message: "设备离线" };
  }
  if (status === "timeout") {
    return { type: "warning", message: `${actionLabel}超时` };
  }
  return { type: "error", message: `${actionLabel}失败` };
}

export function WearableHealthTab({ patientId, projectPatientId }: { patientId: number; projectPatientId: number }) {
  const queryClient = useQueryClient();
  const [metricType, setMetricType] = useState<WearableMetricType>("heart_rate");
  const [bucket, setBucket] = useState<WearableBucket>("raw");
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(rangeDefaults);
  const [feedbackState, setFeedbackState] = useState<ScopedFeedback | null>(null);
  const [checkedStatusState, setCheckedStatusState] =
    useState<ScopedDeviceStatus | null>(null);
  const [pendingOperation, setPendingOperation] =
    useState<PendingOperation | null>(null);
  const actionRequestRef = useRef(0);

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
  const deviceIdentity = syncQuery.isSuccess
    ? isBound
      ? `bound:${syncQuery.data.binding_id}:${syncQuery.data.device_id}`
      : "unbound"
    : "loading";
  const [deviceDraftState, setDeviceDraftState] = useState<DeviceDraftState>(
    () => ({
      deviceIdentity,
      ...DEFAULT_DEVICE_DRAFTS,
    }),
  );
  const activeDeviceDrafts =
    deviceDraftState.deviceIdentity === deviceIdentity
      ? deviceDraftState
      : { deviceIdentity, ...DEFAULT_DEVICE_DRAFTS };
  const updateDeviceDrafts = (
    update: Partial<Omit<DeviceDraftState, "deviceIdentity">>,
  ) => {
    setDeviceDraftState((current) => ({
      ...(current.deviceIdentity === deviceIdentity
        ? current
        : DEFAULT_DEVICE_DRAFTS),
      deviceIdentity,
      ...update,
    }));
  };
  const {
    heartRateInterval,
    bloodPressureInterval,
    bloodOxygenInterval,
    stepEnabled,
  } = activeDeviceDrafts;
  const actionScopeKey = [
    patientId,
    projectPatientId,
    deviceIdentity,
    metricType,
    bucket,
    params.start,
    params.end,
  ].join(":");
  const currentActionScopeKey = useRef(actionScopeKey);
  if (currentActionScopeKey.current !== actionScopeKey) {
    currentActionScopeKey.current = actionScopeKey;
    actionRequestRef.current += 1;
  }

  useEffect(() => {
    actionRequestRef.current += 1;
    setFeedbackState(null);
    setCheckedStatusState(null);
    setPendingOperation(null);
  }, [actionScopeKey]);

  useEffect(
    () => () => {
      actionRequestRef.current += 1;
    },
    [],
  );

  const deviceIdRef = useRef<number | null>(syncQuery.data?.device_id ?? null);
  const bindingIdRef = useRef<number | null>(syncQuery.data?.binding_id ?? null);
  deviceIdRef.current = syncQuery.data?.device_id ?? null;
  bindingIdRef.current = syncQuery.data?.binding_id ?? null;
  const measurementIdentity: WearableMeasurementQueryIdentity | null =
    isBound &&
    metricType !== "steps" &&
    syncQuery.data?.binding_id != null &&
    syncQuery.data.device_id != null
      ? {
          patientId,
          projectPatientId,
          bindingId: syncQuery.data.binding_id,
          deviceId: syncQuery.data.device_id,
          metricType,
          bucket,
          start: params.start,
          end: params.end,
        }
      : null;
  const measurementsQuery = useQuery({
    queryKey: measurementIdentity
      ? wearableMeasurementQueryKey(measurementIdentity)
      : ["wearable-measurements", "disabled", patientId, projectPatientId],
    enabled: measurementIdentity != null,
    queryFn: ({ signal }) => {
      if (!measurementIdentity) {
        throw new Error("当前没有可用的穿戴设备测量查询。");
      }
      return fetchWearableMeasurementsByIdentity({
        identity: measurementIdentity,
        signal,
      });
    },
  });
  const dailyQuery = useQuery({
    queryKey: ["wearable-daily-summaries", patientId, projectPatientId, params],
    enabled: isBound,
    queryFn: async () =>
      (await apiClient.get<WearableDailySummaryResponse>(`/wearables/patients/${patientId}/daily-summaries/`, { params })).data,
  });

  const measurementCapability = metricType === "steps" ? false : syncQuery.data?.capabilities?.[`measure_${metricType}`] === true;
  const measurementReady =
    measurementIdentity != null &&
    measurementsQuery.isSuccess &&
    !measurementsQuery.isFetching;
  const pendingAction =
    pendingOperation?.scopeKey === actionScopeKey
      ? pendingOperation.action
      : null;
  const operationBusy = pendingAction != null;
  const feedback =
    feedbackState?.scopeKey === actionScopeKey ? feedbackState.value : null;
  const checkedStatus =
    checkedStatusState?.scopeKey === actionScopeKey
      ? checkedStatusState.value
      : null;
  const changeMetric = (value: WearableMetricType) => {
    setMetricType(value);
    setDateRange((current) => clampHealthDateRange(current, value));
  };
  const startRequest = (
    requiresMeasurement = false,
  ): ActionRequest | null => {
    const deviceId = syncQuery.data?.device_id;
    const bindingId = syncQuery.data?.binding_id;
    if (
      operationBusy ||
      !isBound ||
      deviceId == null ||
      bindingId == null ||
      (requiresMeasurement && !measurementReady)
    ) {
      return null;
    }
    const id = actionRequestRef.current + 1;
    actionRequestRef.current = id;
    return {
      id,
      scopeKey: actionScopeKey,
      patientId,
      projectPatientId,
      metricType,
      deviceId,
      bindingId,
      measurementIdentity,
    };
  };

  const isCurrentRequest = (request: ActionRequest) => {
    const cachedStatus =
      queryClient.getQueryData<PatientWearableSyncStatus>([
        "wearable-sync-status",
        request.patientId,
      ]);
    return (
      actionRequestRef.current === request.id &&
      currentActionScopeKey.current === request.scopeKey &&
      patientId === request.patientId &&
      projectPatientId === request.projectPatientId &&
      metricType === request.metricType &&
      deviceIdRef.current === request.deviceId &&
      bindingIdRef.current === request.bindingId &&
      cachedStatus?.is_bound === true &&
      cachedStatus.binding_id === request.bindingId &&
      cachedStatus.device_id === request.deviceId
    );
  };

  const invalidateHealthQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["wearable-sync-status", patientId],
      }),
      queryClient.invalidateQueries({
        queryKey: [
          "wearable-measurements",
          patientId,
          projectPatientId,
        ],
      }),
      queryClient.invalidateQueries({
        queryKey: [
          "wearable-daily-summaries",
          patientId,
          projectPatientId,
        ],
      }),
    ]);
  };

  const pollForMeasurement = async (
    request: ActionRequest,
    baselineSignature: string,
  ) => {
    const identity = request.measurementIdentity;
    if (!identity) return;
    for (let attempt = 0; attempt < MEASUREMENT_POLL_ATTEMPTS; attempt += 1) {
      await waitForPollInterval();
      if (!isCurrentRequest(request)) return;
      let result;
      try {
        result = await queryClient.fetchQuery({
          queryKey: wearableMeasurementQueryKey(identity),
          queryFn: ({ signal }) =>
            fetchWearableMeasurementsByIdentity({ identity, signal }),
          staleTime: 0,
        });
      } catch (error) {
        if (isCurrentRequest(request)) {
          setFeedbackState({
            scopeKey: request.scopeKey,
            value: {
              type: "error",
              message: errorMessage(
                error,
                "刷新主动测量趋势失败，请稍后重试。",
              ),
            },
          });
        }
        return;
      }
      if (!isCurrentRequest(request)) return;
      if (measurementSignature(result) !== baselineSignature) {
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: [
              "wearable-daily-summaries",
              request.patientId,
              request.projectPatientId,
            ],
          }),
          queryClient.invalidateQueries({
            queryKey: ["wearable-sync-status", request.patientId],
          }),
        ]);
        if (isCurrentRequest(request)) {
          const metricLabel =
            METRIC_OPTIONS.find(
              (option) => option.value === request.metricType,
            )?.label ?? "健康";
          setFeedbackState({
            scopeKey: request.scopeKey,
            value: {
              type: "success",
              message: `已获取新的${metricLabel}测量点。`,
            },
          });
        }
        return;
      }
    }
    if (isCurrentRequest(request)) {
      setFeedbackState({
        scopeKey: request.scopeKey,
        value: {
          type: "warning",
          message: "等待窗口内尚未发现新测量点，请稍后查看。",
        },
      });
    }
  };

  const runAction = async (action: "status" | "measure" | "sync") => {
    const request = startRequest(action === "measure");
    if (!request) return;
    const baselineSignature = request.measurementIdentity
      ? measurementSignature(
          queryClient.getQueryData(
            wearableMeasurementQueryKey(request.measurementIdentity),
          ),
        )
      : measurementSignature(undefined);
    setPendingOperation({ scopeKey: request.scopeKey, action });
    setFeedbackState(null);
    try {
      if (action === "status") {
        const status = (
          await apiClient.post<WearableStatus>(
            `/wearables/devices/${request.deviceId}/check-status/`,
          )
        ).data;
        if (isCurrentRequest(request) && status.device_id === request.deviceId) {
          setCheckedStatusState({
            scopeKey: request.scopeKey,
            value: status,
          });
          setFeedbackState({
            scopeKey: request.scopeKey,
            value: {
              type: status.online ? "success" : "warning",
              message: status.online
                ? "通信测试完成，设备当前在线。"
                : "通信测试完成，设备当前离线。",
              description: `电量：${status.battery_level ?? "—"}%；最近通信：${formatShanghaiDateTime(status.last_communication_at)}`,
            },
          });
          await queryClient.invalidateQueries({
            queryKey: ["wearable-sync-status", request.patientId],
          });
        }
      }
      if (action === "measure") {
        const command = (
          await apiClient.post<WearableCommandResponse>(
            `/wearables/patients/${request.patientId}/measure/`,
            { metric_type: request.metricType },
          )
        ).data;
        if (!isCurrentRequest(request)) return;
        setFeedbackState({
          scopeKey: request.scopeKey,
          value: commandFeedback(command.status, "主动测量"),
        });
        if (command.status === "succeeded" || command.status === "queued") {
          await pollForMeasurement(request, baselineSignature);
        }
      }
      if (action === "sync") {
        const result = (
          await apiClient.post<WearableSyncCommandResponse>(
            `/wearables/patients/${request.patientId}/sync/`,
            { metric_type: request.metricType },
          )
        ).data;
        if (isCurrentRequest(request) && result.status === "queued") {
          setFeedbackState({
            scopeKey: request.scopeKey,
            value: {
              type: "info",
              message: "健康数据同步已排队，尚未确认新数据到达。",
            },
          });
          await invalidateHealthQueries();
        }
      }
    } catch (error) {
      if (isCurrentRequest(request)) {
        setFeedbackState({
          scopeKey: request.scopeKey,
          value: {
            type: "error",
            message: errorMessage(error, "设备操作失败，请稍后重试。"),
          },
        });
      }
    } finally {
      if (isCurrentRequest(request)) setPendingOperation(null);
    }
  };

  const runConfigure = async (
    action: string,
    label: string,
    payload: Record<string, unknown>,
  ) => {
    const request = startRequest();
    if (!request) return;
    setPendingOperation({ scopeKey: request.scopeKey, action });
    setFeedbackState(null);
    try {
      const command = (
        await apiClient.post<WearableCommandResponse>(
          `/wearables/patients/${request.patientId}/configure/`,
          payload,
        )
      ).data;
      if (isCurrentRequest(request)) {
        setFeedbackState({
          scopeKey: request.scopeKey,
          value: commandFeedback(command.status, label),
        });
      }
    } catch (error) {
      if (isCurrentRequest(request)) {
        setFeedbackState({
          scopeKey: request.scopeKey,
          value: {
            type: "error",
            message: errorMessage(error, "设备配置失败，请稍后重试。"),
          },
        });
      }
    } finally {
      if (isCurrentRequest(request)) setPendingOperation(null);
    }
  };

  if (syncQuery.isLoading) return <Spin />;
  if (syncQuery.isError) return <Alert type="error" showIcon message={errorMessage(syncQuery.error, "加载穿戴健康摘要失败")} />;
  const syncStatus = syncQuery.data;
  if (!syncStatus?.is_bound) return <Empty description="请先在患者接入中绑定穿戴设备。" />;

  const metricName = METRIC_OPTIONS.find((option) => option.value === metricType)?.label;
  const latestDeviceStatus = checkedStatus
    ? checkedStatus.online
      ? "online"
      : "offline"
    : syncStatus.last_device_status;
  const latestBattery = checkedStatus?.battery_level ?? syncStatus.last_battery_level;
  const latestCommunication =
    checkedStatus?.last_communication_at ?? syncStatus.last_communication_at;
  const deviceStatusLabel =
    latestDeviceStatus === "online"
      ? "设备在线"
      : latestDeviceStatus === "offline"
        ? "设备离线"
        : "状态未知";
  const capabilities = syncStatus.capabilities;
  const validInterval = (value: number | null) =>
    value != null && Number.isInteger(value) && value >= 1 && value <= 1440;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Descriptions
        size="small"
        column={{ xs: 1, sm: 2, lg: 4 }}
        items={[
          { key: "device", label: "绑定设备", children: `设备 ${syncStatus.device_short_code ?? "—"}` },
          { key: "model", label: "设备型号", children: syncStatus.model ?? "—" },
          { key: "deviceStatus", label: "通信状态", children: deviceStatusLabel },
          { key: "battery", label: "设备电量", children: latestBattery == null ? "—" : `${latestBattery}%` },
          { key: "communication", label: "最近通信", children: formatShanghaiDateTime(latestCommunication) },
          { key: "sync", label: "最近健康同步", children: formatShanghaiDateTime(syncStatus.last_sync_at) },
          { key: "status", label: "指标", children: metricName },
        ]}
      />
      <Space wrap>
        <DatePicker.RangePicker
          aria-label="健康日期范围"
          value={dateRange}
          disabledDate={(current, info) =>
            isOutsideHealthRange(current, info.from, metricType)
          }
          onChange={(value) =>
            value?.[0] &&
            value?.[1] &&
            setDateRange(clampHealthDateRange([value[0], value[1]], metricType))
          }
        />
        <Select aria-label="健康指标" value={metricType} options={METRIC_OPTIONS} onChange={changeMetric} style={{ width: 120 }} />
        {metricType !== "steps" ? <Select aria-label="图表间隔" value={bucket} options={BUCKET_OPTIONS} onChange={setBucket} style={{ width: 120 }} /> : null}
        <Button
          icon={<WifiOutlined />}
          disabled={operationBusy}
          loading={pendingAction === "status"}
          onClick={() => void runAction("status")}
        >
          通信测试
        </Button>
        {metricType !== "steps" ? (
          <Button
            disabled={
              operationBusy ||
              !measurementCapability ||
              !measurementReady
            }
            loading={pendingAction === "measure"}
            onClick={() => void runAction("measure")}
          >
            主动测量
          </Button>
        ) : null}
        <Button
          icon={<ReloadOutlined />}
          disabled={operationBusy}
          loading={pendingAction === "sync"}
          onClick={() => void runAction("sync")}
        >
          主动同步
        </Button>
      </Space>
      {metricType !== "steps" && !measurementCapability ? <Alert type="info" showIcon message="该型号能力尚未验证" /> : null}
      {feedback ? <Alert type={feedback.type} showIcon message={feedback.message} description={feedback.description} /> : null}
      <Typography.Title level={5} style={{ margin: 0 }}>设备配置</Typography.Title>
      <Typography.Text type="secondary">
        以下为待下发值，不代表已读取设备当前配置。
      </Typography.Text>
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Space wrap>
          <Typography.Text style={{ width: 150 }}>心率采集间隔</Typography.Text>
          <InputNumber
            aria-label="心率间隔（分钟）"
            min={1}
            max={1440}
            precision={0}
            value={heartRateInterval}
            onChange={(value) =>
              updateDeviceDrafts({ heartRateInterval: value })
            }
          />
          <Button
            disabled={
              operationBusy ||
              !capabilities.configure_heart_rate_interval ||
              !validInterval(heartRateInterval)
            }
            loading={pendingAction === "configure-heart-rate"}
            onClick={() =>
              void runConfigure(
                "configure-heart-rate",
                "心率间隔配置",
                {
                  setting: "heart_rate_interval",
                  interval_minutes: heartRateInterval,
                },
              )
            }
          >
            应用心率间隔
          </Button>
          {!capabilities.configure_heart_rate_interval ? (
            <Typography.Text type="secondary">该型号能力尚未验证</Typography.Text>
          ) : null}
        </Space>
        <Space wrap>
          <Typography.Text style={{ width: 150 }}>血压采集间隔</Typography.Text>
          <InputNumber
            aria-label="血压间隔（分钟）"
            min={1}
            max={1440}
            precision={0}
            value={bloodPressureInterval}
            onChange={(value) =>
              updateDeviceDrafts({ bloodPressureInterval: value })
            }
          />
          <Button
            disabled={
              operationBusy ||
              !capabilities.configure_blood_pressure_interval ||
              !validInterval(bloodPressureInterval)
            }
            loading={pendingAction === "configure-blood-pressure"}
            onClick={() =>
              void runConfigure(
                "configure-blood-pressure",
                "血压间隔配置",
                {
                  setting: "blood_pressure_interval",
                  interval_minutes: bloodPressureInterval,
                },
              )
            }
          >
            应用血压间隔
          </Button>
          {!capabilities.configure_blood_pressure_interval ? (
            <Typography.Text type="secondary">该型号能力尚未验证</Typography.Text>
          ) : null}
        </Space>
        <Space wrap>
          <Typography.Text style={{ width: 150 }}>血氧采集间隔</Typography.Text>
          <InputNumber
            aria-label="血氧间隔（分钟）"
            min={1}
            max={1440}
            precision={0}
            value={bloodOxygenInterval}
            onChange={(value) =>
              updateDeviceDrafts({ bloodOxygenInterval: value })
            }
          />
          <Button
            disabled={
              operationBusy ||
              !capabilities.configure_blood_oxygen_interval ||
              !validInterval(bloodOxygenInterval)
            }
            loading={pendingAction === "configure-blood-oxygen"}
            onClick={() =>
              void runConfigure(
                "configure-blood-oxygen",
                "血氧间隔配置",
                {
                  setting: "blood_oxygen_interval",
                  interval_minutes: bloodOxygenInterval,
                },
              )
            }
          >
            应用血氧间隔
          </Button>
          {!capabilities.configure_blood_oxygen_interval ? (
            <Typography.Text type="secondary">该型号能力尚未验证</Typography.Text>
          ) : null}
        </Space>
        <Space wrap>
          <Typography.Text style={{ width: 150 }}>步数开关</Typography.Text>
          <Select
            aria-label="步数开关待下发值"
            value={stepEnabled}
            onChange={(value) =>
              updateDeviceDrafts({ stepEnabled: value })
            }
            style={{ width: 120 }}
            options={[
              { value: true, label: "开启", title: "开启" },
              { value: false, label: "关闭", title: "关闭" },
            ]}
          />
          <Button
            disabled={operationBusy || !capabilities.configure_step_switch}
            loading={pendingAction === "configure-steps"}
            onClick={() =>
              void runConfigure("configure-steps", "步数开关配置", {
                setting: "step_switch",
                enabled: stepEnabled,
              })
            }
          >
            应用步数开关
          </Button>
          {!capabilities.configure_step_switch ? (
            <Typography.Text type="secondary">该型号能力尚未验证</Typography.Text>
          ) : null}
        </Space>
      </Space>
      <Typography.Title level={5} style={{ margin: 0 }}>健康趋势</Typography.Title>
      {metricType === "steps" ? (
        dailyQuery.isLoading ? (
          <LoadingState label="正在加载健康趋势" />
        ) : dailyQuery.isError ? (
          <Alert type="error" showIcon message={errorMessage(dailyQuery.error, "加载步数趋势失败")} />
        ) : (
          <WearableStepsChart data={dailyQuery.data} />
        )
      ) : measurementsQuery.isLoading ? (
        <LoadingState label="正在加载健康趋势" />
      ) : measurementsQuery.isError ? (
        <Alert type="error" showIcon message={errorMessage(measurementsQuery.error, "加载健康趋势失败")} />
      ) : (
        <WearableMetricChart metricType={metricType} data={measurementsQuery.data} />
      )}
      <Typography.Title level={5} style={{ margin: 0 }}>日汇总</Typography.Title>
      {dailyQuery.isLoading ? (
        <LoadingState label="正在加载日汇总" />
      ) : dailyQuery.isError ? (
        <Alert type="error" showIcon message={errorMessage(dailyQuery.error, "加载日汇总失败")} />
      ) : (dailyQuery.data?.items.length ?? 0) === 0 ? (
        <Empty description="暂无日汇总数据" />
      ) : (
        <Table<WearableDailySummary>
          rowKey="record_date"
          dataSource={dailyQuery.data?.items ?? []}
          pagination={false}
          scroll={{ x: 760 }}
          columns={dailyColumns(metricType)}
        />
      )}
    </Space>
  );
}
