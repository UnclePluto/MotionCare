import { BellOutlined, DisconnectOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Input, Modal, Space, Typography } from "antd";
import dayjs from "dayjs";
import { useEffect, useRef, useState } from "react";

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

export function WearableBindingPanel({ projectPatientId }: { projectPatientId: number }) {
  const queryClient = useQueryClient();
  const queryKey = ["project-patient-wearable-binding", projectPatientId];
  const currentProjectPatientId = useRef(projectPatientId);
  currentProjectPatientId.current = projectPatientId;
  const previousProjectPatientId = useRef(projectPatientId);
  const statusRequestGeneration = useRef(0);
  const [shortCode, setShortCode] = useState("");
  const [bindingSuccess, setBindingSuccess] = useState(false);
  const [unbindSuccess, setUnbindSuccess] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState<StatusFeedback | null>(null);
  const [unbindOpen, setUnbindOpen] = useState(false);

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
      (await apiClient.post<WearableStatus>(`/wearables/devices/${deviceId}/check-status/`))
        .data,
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

  function runStatusCheck(targetBinding: WearableBinding, targetProjectPatientId: number) {
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
    mutationFn: async ({
      targetProjectPatientId,
      value,
    }: {
      targetProjectPatientId: number;
      value: string;
    }) =>
      (
        await apiClient.post<WearableBinding>(
          `/wearables/project-patients/${targetProjectPatientId}/bind/`,
          {
            short_code: value,
          },
        )
      ).data,
    onSuccess: async (binding, variables) => {
      const targetQueryKey = [
        "project-patient-wearable-binding",
        variables.targetProjectPatientId,
      ];
      await queryClient.cancelQueries({ queryKey: targetQueryKey });
      queryClient.setQueryData<ProjectPatientWearableBinding>(targetQueryKey, {
        project_patient_id: variables.targetProjectPatientId,
        patient_id: binding.patient_id,
        binding,
      });
      void queryClient.invalidateQueries({ queryKey: targetQueryKey });
      if (currentProjectPatientId.current !== variables.targetProjectPatientId) return;
      currentBinding.current = binding;
      previousBindingIdentity.current = `${binding.id}:${binding.device_id}`;
      setBindingSuccess(true);
      setUnbindSuccess(false);
      setShortCode("");
      runStatusCheck(binding, variables.targetProjectPatientId);
    },
  });

  const unbind = useMutation({
    mutationFn: async ({
      bindingId,
    }: {
      targetProjectPatientId: number;
      patientId: number;
      bindingId: number;
    }) =>
      apiClient.post(`/wearables/bindings/${bindingId}/unbind/`, {
        reason: "项目患者页解绑",
      }),
    onSuccess: async (_data, variables) => {
      const targetsCurrent =
        currentProjectPatientId.current === variables.targetProjectPatientId;
      if (targetsCurrent) {
        statusRequestGeneration.current += 1;
        currentBinding.current = null;
        previousBindingIdentity.current = null;
        setStatusFeedback(null);
        statusCheck.reset();
      }
      const targetQueryKey = [
        "project-patient-wearable-binding",
        variables.targetProjectPatientId,
      ];
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
  });

  const ring = useMutation({
    mutationFn: async ({
      deviceId,
    }: {
      targetProjectPatientId: number;
      deviceId: number;
    }) => apiClient.post(`/wearables/devices/${deviceId}/ring/`),
  });
  const { reset: resetBind } = bind;
  const { reset: resetUnbind } = unbind;
  const { reset: resetStatusCheck } = statusCheck;
  const { reset: resetRing } = ring;

  useEffect(() => {
    if (previousBindingIdentity.current === bindingIdentity) return;
    statusRequestGeneration.current += 1;
    setStatusFeedback(null);
    resetStatusCheck();
    previousBindingIdentity.current = bindingIdentity;
  }, [bindingIdentity, resetStatusCheck]);

  useEffect(() => {
    if (previousProjectPatientId.current === projectPatientId) return;
    statusRequestGeneration.current += 1;
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
  }, [
    projectPatientId,
    resetBind,
    resetRing,
    resetStatusCheck,
    resetUnbind,
  ]);

  const bindTargetsCurrent =
    bind.variables?.targetProjectPatientId === projectPatientId;
  const unbindTargetsCurrent =
    unbind.variables?.targetProjectPatientId === projectPatientId;
  const statusTargetsCurrent =
    statusCheck.variables?.targetProjectPatientId === projectPatientId &&
    statusCheck.variables.generation === statusRequestGeneration.current &&
    statusCheck.variables.bindingId === binding?.id &&
    statusCheck.variables.deviceId === binding.device_id;
  const ringTargetsCurrent =
    ring.variables?.targetProjectPatientId === projectPatientId;
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
  const submitBind = () => {
    if (!canBind) return;
    bind.mutate({
      targetProjectPatientId: projectPatientId,
      value: shortCode,
    });
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Text strong>穿戴设备</Typography.Text>
        {binding ? (
          <Space wrap>
            <Button
              aria-label="通信测试"
              icon={<ReloadOutlined />}
              loading={statusCheck.isPending && statusTargetsCurrent}
              onClick={() => runStatusCheck(binding, projectPatientId)}
            >
              通信测试
            </Button>
            {canRing ? (
              <Button
                aria-label="让设备响铃"
                icon={<BellOutlined />}
                loading={ring.isPending && ringTargetsCurrent}
                onClick={() =>
                  ring.mutate({
                    targetProjectPatientId: projectPatientId,
                    deviceId: binding.device_id,
                  })
                }
              >
                让设备响铃
              </Button>
            ) : null}
            <Button aria-label="解绑设备" danger icon={<DisconnectOutlined />} onClick={() => setUnbindOpen(true)}>
              解绑设备
            </Button>
          </Space>
        ) : null}
      </Space>

      {bindingQuery.isPending ? (
        <Alert type="info" showIcon message="设备绑定状态加载中" />
      ) : binding ? (
        <Descriptions size="small" bordered column={{ xs: 1, sm: 2 }}>
          <Descriptions.Item label="当前设备">{binding.short_code}</Descriptions.Item>
          <Descriptions.Item label="绑定时间">{formatTime(binding.bound_at)}</Descriptions.Item>
        </Descriptions>
      ) : (
        <Space.Compact style={{ width: "100%" }}>
          <Input
            aria-label="设备固定简码"
            inputMode="numeric"
            maxLength={4}
            placeholder="设备固定简码"
            value={shortCode}
            onChange={(event) => setShortCode(event.target.value.replace(/\D/g, ""))}
            onPressEnter={submitBind}
          />
          <Button
            type="primary"
            loading={bind.isPending && bindTargetsCurrent}
            disabled={!canBind}
            onClick={submitBind}
          >
            绑定设备
          </Button>
        </Space.Compact>
      )}

      {bindingSuccess ? <Alert type="success" showIcon message="患者设备绑定成功" /> : null}
      {unbindSuccess ? <Alert type="success" showIcon message="设备解绑成功" /> : null}
      {bind.isError && bindTargetsCurrent ? <Alert type="error" showIcon message={errorMessage(bind.error, "设备绑定失败")} /> : null}
      {bindingQuery.isError ? <Alert type="error" showIcon message={errorMessage(bindingQuery.error, "设备绑定状态加载失败")} /> : null}
      {statusError ? <Alert type="warning" showIcon message={errorMessage(statusError, "设备通信测试失败")} /> : null}
      {statusResult ? (
        <Alert
          type={statusResult.online ? "success" : "warning"}
          showIcon
          message={statusResult.online ? "设备通信正常" : "设备通信异常"}
          description={`最近通信：${formatTime(statusResult.last_communication_at)}；电量：${statusResult.battery_level ?? "—"}%`}
        />
      ) : null}
      {ring.isError && ringTargetsCurrent ? <Alert type="warning" showIcon message={errorMessage(ring.error, "设备响铃请求失败")} /> : null}

      <Modal
        open={unbindOpen}
        title="确认解绑设备"
        okText="确认解绑"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: unbind.isPending && unbindTargetsCurrent }}
        onCancel={() => setUnbindOpen(false)}
        onOk={() =>
          binding &&
          unbind.mutate({
            targetProjectPatientId: projectPatientId,
            patientId: binding.patient_id,
            bindingId: binding.id,
          })
        }
      >
        <Typography.Paragraph>解绑后，设备将停止为该患者归属新的数据。</Typography.Paragraph>
        <Typography.Paragraph strong>历史研究数据不会删除。</Typography.Paragraph>
        {unbind.isError && unbindTargetsCurrent ? <Alert type="error" showIcon message={errorMessage(unbind.error, "设备解绑失败")} /> : null}
      </Modal>
    </Space>
  );
}
