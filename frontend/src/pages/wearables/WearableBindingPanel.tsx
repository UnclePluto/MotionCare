import { BellOutlined, DisconnectOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Input, Modal, Space, Typography } from "antd";
import dayjs from "dayjs";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { apiClient } from "../../api/client";
import type { ProjectPatientWearableBinding, WearableBinding, WearableStatus } from "./types";

function errorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const data = (error as { response?: { data?: unknown } }).response?.data;
    const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : undefined;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function formatTime(value: string | null | undefined) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";
}

type StatusRequest = {
  targetProjectPatientId: number;
  bindingId: number;
  deviceId: number;
  generation: number;
};

type StatusFeedback = StatusRequest & {
  result: WearableStatus | null;
  error: unknown | null;
};

export type WearableBindingView = {
  binding: WearableBinding | null;
  isLoading: boolean;
  bindOpen: boolean;
  shortCode: string;
  canBind: boolean;
  bindPending: boolean;
  statusPending: boolean;
  canRing: boolean;
  ringPending: boolean;
  unbindOpen: boolean;
  unbindPending: boolean;
  openBind: () => void;
  closeBind: () => void;
  setShortCode: (value: string) => void;
  submitBind: () => void;
  runStatusCheck: () => void;
  requestRing: () => void;
  openUnbind: () => void;
  closeUnbind: () => void;
  confirmUnbind: () => void;
  feedback: {
    bindingSuccess: boolean;
    unbindSuccess: boolean;
    bindError: string | null;
    queryError: string | null;
    statusError: string | null;
    statusResult: WearableStatus | null;
    ringError: string | null;
    unbindError: string | null;
  };
};

const WearableBindingContext = createContext<WearableBindingView | null>(null);

export function useWearableBindingView(): WearableBindingView {
  const view = useContext(WearableBindingContext);
  if (!view) throw new Error("useWearableBindingView 必须在 WearableBindingProvider 内使用");
  return view;
}

export function WearableBindingProvider({
  projectPatientId,
  children,
}: {
  projectPatientId: number;
  children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const queryKey = ["project-patient-wearable-binding", projectPatientId];
  const currentProjectPatientId = useRef(projectPatientId);
  currentProjectPatientId.current = projectPatientId;
  const previousProjectPatientId = useRef(projectPatientId);
  const statusRequestGeneration = useRef(0);
  const [bindOpen, setBindOpen] = useState(false);
  const [shortCode, setShortCode] = useState("");
  const [bindingSuccess, setBindingSuccess] = useState(false);
  const [unbindSuccess, setUnbindSuccess] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState<StatusFeedback | null>(null);
  const [unbindOpen, setUnbindOpen] = useState(false);
  const bindRequestsInFlight = useRef(new Set<number>());
  const unbindRequestsInFlight = useRef(new Set<string>());
  const [, setBindInFlightVersion] = useState(0);
  const [, setUnbindInFlightVersion] = useState(0);

  const bindingQuery = useQuery({
    queryKey,
    queryFn: async () =>
      (await apiClient.get<ProjectPatientWearableBinding>(`/wearables/project-patients/${projectPatientId}/binding/`)).data,
  });

  const binding = bindingQuery.data?.binding ?? null;
  const currentBinding = useRef<WearableBinding | null>(binding);
  currentBinding.current = binding;
  const bindingIdentity = binding ? `${binding.id}:${binding.device_id}` : null;
  const previousBindingIdentity = useRef(bindingIdentity);

  const statusCheck = useMutation({
    mutationFn: async ({ deviceId }: StatusRequest) =>
      (await apiClient.post<WearableStatus>(`/wearables/devices/${deviceId}/check-status/`)).data,
    onSuccess: (data, variables) => {
      const activeBinding = currentBinding.current;
      if (
        statusRequestGeneration.current !== variables.generation ||
        currentProjectPatientId.current !== variables.targetProjectPatientId ||
        activeBinding?.id !== variables.bindingId ||
        activeBinding.device_id !== variables.deviceId ||
        data.device_id !== variables.deviceId
      ) return;
      setStatusFeedback({ ...variables, result: data, error: null });
    },
    onError: (error, variables) => {
      const activeBinding = currentBinding.current;
      if (
        statusRequestGeneration.current !== variables.generation ||
        currentProjectPatientId.current !== variables.targetProjectPatientId ||
        activeBinding?.id !== variables.bindingId ||
        activeBinding.device_id !== variables.deviceId
      ) return;
      setStatusFeedback({ ...variables, result: null, error });
    },
  });

  function startStatusCheck(targetBinding: WearableBinding, targetProjectPatientId: number) {
    const generation = statusRequestGeneration.current + 1;
    statusRequestGeneration.current = generation;
    setStatusFeedback(null);
    statusCheck.mutate({
      targetProjectPatientId,
      bindingId: targetBinding.id,
      deviceId: targetBinding.device_id,
      generation,
    });
  }

  const bind = useMutation({
    mutationFn: async ({ targetProjectPatientId, value }: { targetProjectPatientId: number; value: string }) =>
      (await apiClient.post<WearableBinding>(`/wearables/project-patients/${targetProjectPatientId}/bind/`, {
        short_code: value,
      })).data,
    onSuccess: async (newBinding, variables) => {
      const targetQueryKey = ["project-patient-wearable-binding", variables.targetProjectPatientId];
      await queryClient.cancelQueries({ queryKey: targetQueryKey });
      queryClient.setQueryData<ProjectPatientWearableBinding>(targetQueryKey, {
        project_patient_id: variables.targetProjectPatientId,
        patient_id: newBinding.patient_id,
        binding: newBinding,
      });
      void queryClient.invalidateQueries({ queryKey: targetQueryKey });
      if (currentProjectPatientId.current !== variables.targetProjectPatientId) return;
      currentBinding.current = newBinding;
      previousBindingIdentity.current = `${newBinding.id}:${newBinding.device_id}`;
      setBindOpen(false);
      setBindingSuccess(true);
      setUnbindSuccess(false);
      setShortCode("");
      startStatusCheck(newBinding, variables.targetProjectPatientId);
    },
    onSettled: (_data, _error, variables) => {
      if (bindRequestsInFlight.current.delete(variables.targetProjectPatientId)) {
        setBindInFlightVersion((version) => version + 1);
      }
    },
  });

  const unbind = useMutation({
    mutationFn: async ({ bindingId }: { targetProjectPatientId: number; patientId: number; bindingId: number }) =>
      apiClient.post(`/wearables/bindings/${bindingId}/unbind/`, { reason: "项目患者页解绑" }),
    onSuccess: async (_data, variables) => {
      const targetsCurrent = currentProjectPatientId.current === variables.targetProjectPatientId;
      if (targetsCurrent) {
        statusRequestGeneration.current += 1;
        currentBinding.current = null;
        previousBindingIdentity.current = null;
        setStatusFeedback(null);
        statusCheck.reset();
      }
      const targetQueryKey = ["project-patient-wearable-binding", variables.targetProjectPatientId];
      await queryClient.cancelQueries({ queryKey: targetQueryKey });
      queryClient.setQueryData<ProjectPatientWearableBinding>(targetQueryKey, {
        project_patient_id: variables.targetProjectPatientId,
        patient_id: variables.patientId,
        binding: null,
      });
      void queryClient.invalidateQueries({ queryKey: targetQueryKey });
      if (currentProjectPatientId.current !== variables.targetProjectPatientId) return;
      setUnbindOpen(false);
      setBindingSuccess(false);
      setUnbindSuccess(true);
    },
    onSettled: (_data, _error, variables) => {
      const requestKey = `${variables.targetProjectPatientId}:${variables.bindingId}`;
      if (unbindRequestsInFlight.current.delete(requestKey)) {
        setUnbindInFlightVersion((version) => version + 1);
      }
    },
  });

  const ring = useMutation({
    mutationFn: async ({ deviceId }: { targetProjectPatientId: number; deviceId: number }) =>
      apiClient.post(`/wearables/devices/${deviceId}/ring/`),
  });
  const { reset: resetBind } = bind;
  const { reset: resetUnbind } = unbind;
  const { reset: resetStatusCheck } = statusCheck;
  const { reset: resetRing } = ring;
  const closeBind = useCallback(() => {
    setBindOpen(false);
    setShortCode("");
    resetBind();
  }, [resetBind]);

  useEffect(() => {
    if (previousBindingIdentity.current === bindingIdentity) return;
    statusRequestGeneration.current += 1;
    setStatusFeedback(null);
    resetStatusCheck();
    if (binding) closeBind();
    previousBindingIdentity.current = bindingIdentity;
  }, [binding, bindingIdentity, closeBind, resetStatusCheck]);

  useEffect(() => {
    if (previousProjectPatientId.current === projectPatientId) return;
    statusRequestGeneration.current += 1;
    setBindOpen(false);
    setShortCode("");
    setBindingSuccess(false);
    setUnbindSuccess(false);
    setStatusFeedback(null);
    setUnbindOpen(false);
    resetBind();
    resetUnbind();
    resetStatusCheck();
    resetRing();
    previousProjectPatientId.current = projectPatientId;
  }, [projectPatientId, resetBind, resetRing, resetStatusCheck, resetUnbind]);

  const bindTargetsCurrent = bind.variables?.targetProjectPatientId === projectPatientId;
  const unbindTargetsCurrent = unbind.variables?.targetProjectPatientId === projectPatientId;
  const statusTargetsCurrent =
    statusCheck.variables?.targetProjectPatientId === projectPatientId &&
    statusCheck.variables.generation === statusRequestGeneration.current &&
    statusCheck.variables.bindingId === binding?.id &&
    statusCheck.variables.deviceId === binding.device_id;
  const ringTargetsCurrent = ring.variables?.targetProjectPatientId === projectPatientId;
  const activeStatusFeedback =
    statusFeedback &&
    statusFeedback.targetProjectPatientId === projectPatientId &&
    statusFeedback.generation === statusRequestGeneration.current &&
    statusFeedback.bindingId === binding?.id &&
    statusFeedback.deviceId === binding.device_id
      ? statusFeedback
      : null;
  const statusResult = activeStatusFeedback?.result ?? null;
  const statusError = activeStatusFeedback?.error ?? null;
  const canRing = statusResult?.capabilities?.ring === true;
  const canBind = /^\d{4}$/.test(shortCode);
  const isLoading = bindingQuery.isPending;
  const bindPending = bindRequestsInFlight.current.has(projectPatientId);
  const statusPending = statusCheck.isPending && statusTargetsCurrent;
  const ringPending = ring.isPending && ringTargetsCurrent;
  const unbindRequestKey = binding ? `${projectPatientId}:${binding.id}` : null;
  const unbindPending = unbindRequestKey
    ? unbindRequestsInFlight.current.has(unbindRequestKey)
    : false;
  const submitBind = () => {
    if (
      isLoading ||
      currentBinding.current ||
      !canBind ||
      bindRequestsInFlight.current.has(projectPatientId)
    ) return;
    bindRequestsInFlight.current.add(projectPatientId);
    setBindInFlightVersion((version) => version + 1);
    bind.mutate({ targetProjectPatientId: projectPatientId, value: shortCode });
  };
  const confirmUnbind = () => {
    if (!binding || !unbindRequestKey || unbindRequestsInFlight.current.has(unbindRequestKey)) return;
    unbindRequestsInFlight.current.add(unbindRequestKey);
    setUnbindInFlightVersion((version) => version + 1);
    unbind.mutate({
      targetProjectPatientId: projectPatientId,
      patientId: binding.patient_id,
      bindingId: binding.id,
    });
  };

  const view: WearableBindingView = {
    binding,
    isLoading,
    bindOpen,
    shortCode,
    canBind,
    bindPending,
    statusPending,
    canRing,
    ringPending,
    unbindOpen,
    unbindPending,
    openBind: () => {
      if (isLoading || currentBinding.current) return;
      setBindOpen(true);
    },
    closeBind,
    setShortCode,
    submitBind,
    runStatusCheck: () => binding && startStatusCheck(binding, projectPatientId),
    requestRing: () => binding && ring.mutate({ targetProjectPatientId: projectPatientId, deviceId: binding.device_id }),
    openUnbind: () => setUnbindOpen(true),
    closeUnbind: () => setUnbindOpen(false),
    confirmUnbind,
    feedback: {
      bindingSuccess,
      unbindSuccess,
      bindError: bind.isError && bindTargetsCurrent ? errorMessage(bind.error, "设备绑定失败") : null,
      queryError: bindingQuery.isError ? errorMessage(bindingQuery.error, "设备绑定状态加载失败") : null,
      statusError: statusError ? errorMessage(statusError, "设备通信测试失败") : null,
      statusResult,
      ringError: ring.isError && ringTargetsCurrent ? errorMessage(ring.error, "设备响铃请求失败") : null,
      unbindError: unbind.isError && unbindTargetsCurrent ? errorMessage(unbind.error, "设备解绑失败") : null,
    },
  };

  return <WearableBindingContext.Provider value={view}>{children}</WearableBindingContext.Provider>;
}

export function WearableBindingActions() {
  const view = useWearableBindingView();
  if (view.isLoading) return null;
  if (!view.binding) return <Button onClick={view.openBind}>绑定穿戴设备</Button>;
  return (
    <Space wrap>
      <Button aria-label="通信测试" icon={<ReloadOutlined />} loading={view.statusPending} onClick={view.runStatusCheck}>
        通信测试
      </Button>
      {view.canRing ? (
        <Button aria-label="让设备响铃" icon={<BellOutlined />} loading={view.ringPending} onClick={view.requestRing}>
          让设备响铃
        </Button>
      ) : null}
      <Button aria-label="解绑设备" danger icon={<DisconnectOutlined />} onClick={view.openUnbind}>
        解绑设备
      </Button>
    </Space>
  );
}

export function WearableBindingFeedback() {
  const { isLoading, feedback } = useWearableBindingView();
  return (
    <>
      {isLoading ? <Alert type="info" showIcon message="设备绑定状态加载中" /> : null}
      {feedback.bindingSuccess ? <Alert type="success" showIcon message="患者设备绑定成功" /> : null}
      {feedback.unbindSuccess ? <Alert type="success" showIcon message="设备解绑成功" /> : null}
      {feedback.queryError ? <Alert type="error" showIcon message={feedback.queryError} /> : null}
      {feedback.statusError ? <Alert type="warning" showIcon message={feedback.statusError} /> : null}
      {feedback.statusResult ? (
        <Alert
          type={feedback.statusResult.online ? "success" : "warning"}
          showIcon
          message={feedback.statusResult.online ? "设备通信正常" : "设备通信异常"}
          description={`最近通信：${formatTime(feedback.statusResult.last_communication_at)}；电量：${feedback.statusResult.battery_level ?? "—"}%`}
        />
      ) : null}
      {feedback.ringError ? <Alert type="warning" showIcon message={feedback.ringError} /> : null}
    </>
  );
}

export function WearableBindingModals() {
  const view = useWearableBindingView();
  return (
    <>
      <Modal
        open={view.bindOpen}
        title="绑定穿戴设备"
        okText="确认绑定"
        cancelText="取消"
        confirmLoading={view.bindPending}
        okButtonProps={{ disabled: !view.canBind || view.bindPending || Boolean(view.binding) }}
        onCancel={view.closeBind}
        onOk={view.submitBind}
      >
        <label style={{ display: "block" }}>
          <Typography.Text>设备固定简码</Typography.Text>
          <Input
            aria-label="设备固定简码"
            inputMode="numeric"
            maxLength={4}
            placeholder="设备固定简码"
            value={view.shortCode}
            disabled={view.bindPending}
            onChange={(event) => view.setShortCode(event.target.value.replace(/\D/g, "").slice(0, 4))}
            onPressEnter={view.submitBind}
          />
        </label>
        {view.feedback.bindError ? <Alert type="error" showIcon message={view.feedback.bindError} /> : null}
      </Modal>
      <Modal
        open={view.unbindOpen}
        title="确认解绑设备"
        okText="确认解绑"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={view.unbindPending}
        onCancel={view.closeUnbind}
        onOk={view.confirmUnbind}
      >
        <Typography.Paragraph>解绑后，设备将停止为该患者归属新的数据。</Typography.Paragraph>
        <Typography.Paragraph strong>历史研究数据不会删除。</Typography.Paragraph>
        {view.feedback.unbindError ? <Alert type="error" showIcon message={view.feedback.unbindError} /> : null}
      </Modal>
    </>
  );
}

function WearableBindingPanelContent() {
  const view = useWearableBindingView();
  const binding = view.isLoading ? null : view.binding;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Text strong>穿戴设备</Typography.Text>
        <WearableBindingActions />
      </Space>
      <Descriptions size="small" bordered column={{ xs: 1, sm: 2 }}>
        <Descriptions.Item label="设备简码">{binding?.short_code ?? "—"}</Descriptions.Item>
        <Descriptions.Item label="设备 ID">{binding?.device_id ?? "—"}</Descriptions.Item>
        <Descriptions.Item label="设备绑定时间">{binding ? formatTime(binding.bound_at) : "—"}</Descriptions.Item>
      </Descriptions>
      <WearableBindingFeedback />
      <WearableBindingModals />
    </Space>
  );
}

export function WearableBindingPanel({ projectPatientId }: { projectPatientId: number }) {
  return (
    <WearableBindingProvider projectPatientId={projectPatientId}>
      <WearableBindingPanelContent />
    </WearableBindingProvider>
  );
}
