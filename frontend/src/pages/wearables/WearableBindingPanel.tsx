import { BellOutlined, DisconnectOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Input, Modal, Space, Typography } from "antd";
import dayjs from "dayjs";
import { useState } from "react";

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

export function WearableBindingPanel({ projectPatientId }: { projectPatientId: number }) {
  const queryClient = useQueryClient();
  const queryKey = ["project-patient-wearable-binding", projectPatientId];
  const [shortCode, setShortCode] = useState("");
  const [bindingSuccess, setBindingSuccess] = useState(false);
  const [statusResult, setStatusResult] = useState<WearableStatus | null>(null);
  const [unbindOpen, setUnbindOpen] = useState(false);

  const bindingQuery = useQuery({
    queryKey,
    queryFn: async () =>
      (await apiClient.get<ProjectPatientWearableBinding>(`/wearables/project-patients/${projectPatientId}/binding/`)).data,
  });

  const statusCheck = useMutation({
    mutationFn: async (deviceId: number) =>
      (await apiClient.post<WearableStatus>(`/wearables/devices/${deviceId}/check-status/`)).data,
    onSuccess: (data) => setStatusResult(data),
  });

  const bind = useMutation({
    mutationFn: async (value: string) =>
      (
        await apiClient.post<WearableBinding>(`/wearables/project-patients/${projectPatientId}/bind/`, {
          short_code: value,
        })
      ).data,
    onSuccess: (binding) => {
      setBindingSuccess(true);
      setShortCode("");
      setStatusResult(null);
      queryClient.setQueryData<ProjectPatientWearableBinding | undefined>(queryKey, (current) =>
        current ? { ...current, binding } : current,
      );
      statusCheck.mutate(binding.device_id);
    },
  });

  const unbind = useMutation({
    mutationFn: async (bindingId: number) =>
      apiClient.post(`/wearables/bindings/${bindingId}/unbind/`, { reason: "项目患者页解绑" }),
    onSuccess: async () => {
      setUnbindOpen(false);
      setBindingSuccess(false);
      setStatusResult(null);
      await queryClient.invalidateQueries({ queryKey });
    },
  });

  const binding = bindingQuery.data?.binding ?? null;
  const canRing = statusResult?.capabilities?.ring === true;
  const ring = useMutation({
    mutationFn: async (deviceId: number) => apiClient.post(`/wearables/devices/${deviceId}/ring/`),
  });

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Text strong>穿戴设备</Typography.Text>
        {binding ? (
          <Space wrap>
            <Button
              aria-label="通信测试"
              icon={<ReloadOutlined />}
              loading={statusCheck.isPending}
              onClick={() => statusCheck.mutate(binding.device_id)}
            >
              通信测试
            </Button>
            {canRing ? (
              <Button aria-label="让设备响铃" icon={<BellOutlined />} loading={ring.isPending} onClick={() => ring.mutate(binding.device_id)}>
                让设备响铃
              </Button>
            ) : null}
            <Button aria-label="解绑设备" danger icon={<DisconnectOutlined />} onClick={() => setUnbindOpen(true)}>
              解绑设备
            </Button>
          </Space>
        ) : null}
      </Space>

      {binding ? (
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
            onPressEnter={() => bind.mutate(shortCode)}
          />
          <Button type="primary" loading={bind.isPending} disabled={!/^\d{4}$/.test(shortCode)} onClick={() => bind.mutate(shortCode)}>
            绑定设备
          </Button>
        </Space.Compact>
      )}

      {bindingSuccess ? <Alert type="success" showIcon message="患者设备绑定成功" /> : null}
      {bind.isError ? <Alert type="error" showIcon message={errorMessage(bind.error, "设备绑定失败")} /> : null}
      {bindingQuery.isError ? <Alert type="error" showIcon message={errorMessage(bindingQuery.error, "设备绑定状态加载失败")} /> : null}
      {statusCheck.isError ? <Alert type="warning" showIcon message={errorMessage(statusCheck.error, "设备通信测试失败")} /> : null}
      {statusResult ? (
        <Alert
          type={statusResult.online ? "success" : "warning"}
          showIcon
          message={statusResult.online ? "设备通信正常" : "设备通信异常"}
          description={`最近通信：${formatTime(statusResult.last_communication_at)}；电量：${statusResult.battery_level ?? "—"}%`}
        />
      ) : null}
      {ring.isError ? <Alert type="warning" showIcon message={errorMessage(ring.error, "设备响铃请求失败")} /> : null}

      <Modal
        open={unbindOpen}
        title="确认解绑设备"
        okText="确认解绑"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: unbind.isPending }}
        onCancel={() => setUnbindOpen(false)}
        onOk={() => binding && unbind.mutate(binding.id)}
      >
        <Typography.Paragraph>解绑后，设备将停止为该患者归属新的数据。</Typography.Paragraph>
        <Typography.Paragraph strong>历史研究数据不会删除。</Typography.Paragraph>
        {unbind.isError ? <Alert type="error" showIcon message={errorMessage(unbind.error, "设备解绑失败")} /> : null}
      </Modal>
    </Space>
  );
}
