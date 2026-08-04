import { ReloadOutlined, WifiOutlined } from "@ant-design/icons";
import {
  useInfiniteQuery,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Empty,
  Row,
  Segmented,
  Space,
  Spin,
  Table,
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
  firstDailySummaryWindow,
  mergeDailySummaryPages,
  nextDailySummaryWindow,
  type DailySummaryWindow,
} from "./wearableDailySummaryPagination";
import {
  fetchWearableMeasurementsByIdentity,
  wearableMeasurementQueryKey,
  type WearableMeasurementQueryIdentity,
} from "./measurementQueries";
import type {
  PatientWearableSyncStatus,
  WearableDailySummary,
  WearableDailySummaryResponse,
  WearableMetricType,
  WearableStatus,
  WearableSyncCommandResponse,
} from "./types";

const METRIC_LABELS: Record<WearableMetricType, string> = {
  heart_rate: "心率",
  blood_pressure: "血压",
  blood_oxygen: "血氧",
  steps: "步数",
};

const MEASUREMENT_METRICS = [
  "heart_rate",
  "blood_pressure",
  "blood_oxygen",
] as const;

export type DatePreset = "7d" | "30d" | "custom";

const DATE_PRESET_OPTIONS = [
  { label: "近 7 天", value: "7d" },
  { label: "近 30 天", value: "30d" },
  { label: "自定义", value: "custom" },
] as const;

function presetRange(days: 7 | 30): [Dayjs, Dayjs] {
  const today = shanghaiToday();
  return [today.subtract(days - 1, "day"), today];
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

function dailyColumns(): TableColumnsType<WearableDailySummary> {
  return [
    { title: "日期", dataIndex: "record_date", fixed: "left", width: 120 },
    { title: "心率均值", dataIndex: "heart_rate_avg", render: valueOrDash },
    { title: "收缩压均值", dataIndex: "systolic_avg", render: valueOrDash },
    { title: "舒张压均值", dataIndex: "diastolic_avg", render: valueOrDash },
    { title: "血氧均值", dataIndex: "blood_oxygen_avg", render: valueOrDash },
    { title: "步数", dataIndex: "steps", render: valueOrDash },
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
  deviceId: number;
  bindingId: number;
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

export function WearableHealthTab({ patientId, projectPatientId }: { patientId: number; projectPatientId: number }) {
  const queryClient = useQueryClient();
  const [datePreset, setDatePreset] = useState<DatePreset>("30d");
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(() =>
    presetRange(30),
  );
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
  const actionScopeKey = [
    patientId,
    projectPatientId,
    syncQuery.data?.binding_id ?? "unbound",
    syncQuery.data?.device_id ?? "unbound",
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
  const measurementIdentities = useMemo(
    () =>
      Object.fromEntries(
        MEASUREMENT_METRICS.map((metricType) => [
          metricType,
          isBound &&
          syncQuery.data?.binding_id != null &&
          syncQuery.data.device_id != null
            ? {
                patientId,
                projectPatientId,
                bindingId: syncQuery.data.binding_id,
                deviceId: syncQuery.data.device_id,
                metricType,
                bucket: "raw" as const,
                start: params.start,
                end: params.end,
              }
            : null,
        ]),
      ) as Record<
        (typeof MEASUREMENT_METRICS)[number],
        WearableMeasurementQueryIdentity | null
      >,
    [
      isBound,
      params.end,
      params.start,
      patientId,
      projectPatientId,
      syncQuery.data,
    ],
  );
  const measurementQueries = useQueries({
    queries: MEASUREMENT_METRICS.map((metricType) => {
      const identity = measurementIdentities[metricType];
      return {
        queryKey: identity
          ? wearableMeasurementQueryKey(identity)
          : ["wearable-measurements", "disabled", patientId, projectPatientId, metricType],
        enabled: identity != null,
        queryFn: ({ signal }: { signal: AbortSignal }) => {
          if (!identity) {
            throw new Error("当前没有可用的穿戴设备测量查询。");
          }
          return fetchWearableMeasurementsByIdentity({ identity, signal });
        },
      };
    }),
  });
  const stepsTrendQuery = useQuery({
    queryKey: [
      "wearable-daily-trend",
      patientId,
      projectPatientId,
      params,
    ],
    enabled: isBound,
    queryFn: async () =>
      (await apiClient.get<WearableDailySummaryResponse>(`/wearables/patients/${patientId}/daily-summaries/`, { params })).data,
  });
  const historyEnabled =
    isBound &&
    syncQuery.data?.binding_id != null &&
    syncQuery.data.bound_at != null;
  const historyTodayDay = shanghaiToday();
  const historyToday = historyTodayDay.format("YYYY-MM-DD");
  const initialHistoryWindow: DailySummaryWindow = syncQuery.data?.bound_at
    ? firstDailySummaryWindow(syncQuery.data.bound_at, historyTodayDay)
    : {
        start: historyToday,
        end: historyToday,
      };
  const dailyHistoryQueryKey = useMemo(
    () =>
      [
        "wearable-daily-history",
        patientId,
        projectPatientId,
        syncQuery.data?.binding_id ?? "unbound",
        syncQuery.data?.bound_at ?? "unbound",
        historyToday,
      ] as const,
    [
      historyToday,
      patientId,
      projectPatientId,
      syncQuery.data?.binding_id,
      syncQuery.data?.bound_at,
    ],
  );
  const dailyHistoryQuery = useInfiniteQuery({
    queryKey: dailyHistoryQueryKey,
    enabled: historyEnabled,
    gcTime: 0,
    initialPageParam: initialHistoryWindow,
    queryFn: async ({ pageParam, signal }) =>
      (
        await apiClient.get<WearableDailySummaryResponse>(
          `/wearables/patients/${patientId}/daily-summaries/`,
          { params: pageParam, signal },
        )
      ).data,
    getNextPageParam: (_lastPage, _allPages, lastPageParam) => {
      const boundAt = syncQuery.data?.bound_at;
      if (!boundAt) return undefined;
      return nextDailySummaryWindow(lastPageParam, boundAt) ?? undefined;
    },
  });
  useEffect(() => {
    const ownedQueryKey = dailyHistoryQueryKey;
    return () => {
      void queryClient.cancelQueries({
        queryKey: ownedQueryKey,
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: ownedQueryKey,
        exact: true,
      });
    };
  }, [dailyHistoryQueryKey, queryClient]);
  const dailyHistoryItems = useMemo(
    () => mergeDailySummaryPages(dailyHistoryQuery.data?.pages ?? []),
    [dailyHistoryQuery.data?.pages],
  );

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
  const startRequest = (): ActionRequest | null => {
    const deviceId = syncQuery.data?.device_id;
    const bindingId = syncQuery.data?.binding_id;
    if (
      operationBusy ||
      !isBound ||
      deviceId == null ||
      bindingId == null
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
      deviceId,
      bindingId,
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
          "wearable-daily-trend",
          patientId,
          projectPatientId,
        ],
      }),
      queryClient.invalidateQueries({
        queryKey: [
          "wearable-daily-history",
          patientId,
          projectPatientId,
          syncQuery.data?.binding_id ?? "unbound",
        ],
      }),
    ]);
  };

  const runStatusCheck = async () => {
    const request = startRequest();
    if (!request) return;
    setPendingOperation({ scopeKey: request.scopeKey, action: "status" });
    setFeedbackState(null);
    try {
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

  const runSyncAll = async () => {
    const request = startRequest();
    if (!request) return;
    setPendingOperation({ scopeKey: request.scopeKey, action: "sync" });
    setFeedbackState(null);
    try {
      const result = (
        await apiClient.post<WearableSyncCommandResponse>(
          `/wearables/patients/${request.patientId}/sync/`,
          {},
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

  if (syncQuery.isLoading) return <Spin />;
  if (syncQuery.isError) return <Alert type="error" showIcon message={errorMessage(syncQuery.error, "加载穿戴健康摘要失败")} />;
  const syncStatus = syncQuery.data;
  if (!syncStatus?.is_bound) return <Empty description="请先在患者接入中绑定穿戴设备。" />;

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
        ]}
      />
      <Space wrap>
        <Segmented
          options={[...DATE_PRESET_OPTIONS]}
          value={datePreset}
          onChange={(value) => {
            const preset = value as DatePreset;
            setDatePreset(preset);
            if (preset === "7d" || preset === "30d") {
              setDateRange(presetRange(preset === "7d" ? 7 : 30));
            }
          }}
        />
        {datePreset === "custom" ? (
          <DatePicker.RangePicker
            aria-label="健康日期范围"
            value={dateRange}
            disabledDate={(current, info) =>
              isOutsideHealthRange(current, info.from, "heart_rate")
            }
            onChange={(value) => {
              if (value?.[0] && value[1]) {
                setDateRange(
                  clampHealthDateRange([value[0], value[1]], "heart_rate"),
                );
              }
            }}
          />
        ) : null}
        <Button
          icon={<WifiOutlined />}
          disabled={operationBusy}
          loading={pendingAction === "status"}
          onClick={() => void runStatusCheck()}
        >
          通信测试
        </Button>
        <Button
          icon={<ReloadOutlined />}
          disabled={operationBusy}
          loading={pendingAction === "sync"}
          onClick={() => void runSyncAll()}
        >
          主动同步
        </Button>
      </Space>
      {feedback ? <Alert type={feedback.type} showIcon message={feedback.message} description={feedback.description} /> : null}
      <Typography.Title level={5} style={{ margin: 0 }}>健康趋势</Typography.Title>
      <Row gutter={[16, 16]}>
        {MEASUREMENT_METRICS.map((metricType, index) => (
          <Col xs={24} xl={12} key={metricType}>
            <Card title={`${METRIC_LABELS[metricType]}趋势`}>
              {measurementQueries[index].isLoading ? (
                <LoadingState label={`正在加载${METRIC_LABELS[metricType]}趋势`} />
              ) : measurementQueries[index].isError ? (
                <Alert
                  type="error"
                  showIcon
                  message={errorMessage(
                    measurementQueries[index].error,
                    `加载${METRIC_LABELS[metricType]}趋势失败`,
                  )}
                />
              ) : (
                <WearableMetricChart
                  metricType={metricType}
                  data={measurementQueries[index].data}
                />
              )}
            </Card>
          </Col>
        ))}
        <Col xs={24} xl={12}>
          <Card title="步数趋势">
            {stepsTrendQuery.isLoading ? (
              <LoadingState label="正在加载步数趋势" />
            ) : stepsTrendQuery.isError ? (
              <Alert
                type="error"
                showIcon
                message={errorMessage(
                  stepsTrendQuery.error,
                  "加载步数趋势失败",
                )}
              />
            ) : (
              <WearableStepsChart data={stepsTrendQuery.data} />
            )}
          </Card>
        </Col>
      </Row>
      <Typography.Title level={5} style={{ margin: 0 }}>日汇总</Typography.Title>
      {dailyHistoryQuery.isLoading ? (
        <LoadingState label="正在加载日汇总" />
      ) : dailyHistoryQuery.isError && dailyHistoryQuery.data == null ? (
        <Space direction="vertical">
          <Alert
            type="error"
            showIcon
            message={errorMessage(
              dailyHistoryQuery.error,
              "加载日汇总失败",
            )}
          />
          <Button
            type="link"
            onClick={() => void dailyHistoryQuery.refetch()}
          >
            重新加载
          </Button>
        </Space>
      ) : dailyHistoryItems.length === 0 ? (
        <Empty description="暂无日汇总数据" />
      ) : (
        <Table<WearableDailySummary>
          rowKey="record_date"
          dataSource={dailyHistoryItems}
          pagination={false}
          columns={dailyColumns()}
          footer={() => (
            <div style={{ textAlign: "center" }}>
              {dailyHistoryQuery.hasNextPage ? (
                <Button
                  type="link"
                  disabled={dailyHistoryQuery.isFetchingNextPage}
                  onClick={() => void dailyHistoryQuery.fetchNextPage()}
                >
                  {dailyHistoryQuery.isFetchNextPageError
                    ? "获取更多失败，点击重试"
                    : dailyHistoryQuery.isFetchingNextPage
                      ? "正在获取…"
                      : "获取更多"}
                </Button>
              ) : (
                <Typography.Text type="secondary">
                  没有更多数据了
                </Typography.Text>
              )}
            </div>
          )}
        />
      )}
    </Space>
  );
}
