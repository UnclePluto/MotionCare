import { DisconnectOutlined, KeyOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Space, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useEffect, useRef } from "react";

import { apiClient } from "../../api/client";
import {
  WearableBindingActions,
  WearableBindingFeedback,
  WearableBindingModals,
  WearableBindingProvider,
  useWearableBindingView,
} from "../wearables/WearableBindingPanel";

type BindingStatus = {
  has_active_session: boolean;
  has_active_binding_code: boolean;
  binding_code_expires_at: string | null;
  last_bound_at: string | null;
  active_session_expires_at: string | null;
};

type BindingCodeResponse = {
  code: string;
  expires_at: string;
};

type BindingCodeDisplay = BindingCodeResponse & {
  projectPatientId: number;
};

function formatTime(value: string | null | undefined) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";
}

function PatientBindingDescriptions({ status }: { status: BindingStatus | undefined }) {
  const wearableBinding = useWearableBindingView();
  const binding = wearableBinding.isLoading ? null : wearableBinding.binding;

  return (
    <Descriptions size="small" bordered column={{ xs: 1, sm: 3 }}>
      <Descriptions.Item label="患者绑定状态">{status?.has_active_session ? <Tag color="green">已绑定</Tag> : <Tag>未绑定</Tag>}</Descriptions.Item>
      <Descriptions.Item label="有效绑定码">{status?.has_active_binding_code ? <Tag color="blue">存在</Tag> : <Tag>无</Tag>}</Descriptions.Item>
      <Descriptions.Item label="最近绑定时间">{formatTime(status?.last_bound_at)}</Descriptions.Item>
      <Descriptions.Item label="绑定码过期时间">{formatTime(status?.binding_code_expires_at)}</Descriptions.Item>
      <Descriptions.Item label="登录过期时间">{formatTime(status?.active_session_expires_at)}</Descriptions.Item>
      <Descriptions.Item label="设备简码">{binding?.short_code ?? "—"}</Descriptions.Item>
      <Descriptions.Item label="设备 ID">{binding?.device_id ?? "—"}</Descriptions.Item>
      <Descriptions.Item label="设备绑定时间">{binding ? formatTime(binding.bound_at) : "—"}</Descriptions.Item>
    </Descriptions>
  );
}

function MiniappBindingSection({ projectPatientId }: { projectPatientId: number }) {
  const queryClient = useQueryClient();
  const queryKey = ["project-patient-binding-status", projectPatientId];
  const statusQuery = useQuery({
    queryKey,
    queryFn: async () =>
      (await apiClient.get<BindingStatus>(`/studies/project-patients/${projectPatientId}/binding-status/`)).data,
  });
  const createCode = useMutation({
    mutationFn: async (targetProjectPatientId: number): Promise<BindingCodeDisplay> => {
      const response = await apiClient.post<BindingCodeResponse>(
        `/studies/project-patients/${targetProjectPatientId}/binding-code/`,
      );
      return { ...response.data, projectPatientId: targetProjectPatientId };
    },
    onSuccess: (_data, targetProjectPatientId) =>
      queryClient.invalidateQueries({ queryKey: ["project-patient-binding-status", targetProjectPatientId] }),
  });
  const { reset: resetCreateCode } = createCode;
  const previousProjectPatientId = useRef(projectPatientId);

  useEffect(() => {
    if (previousProjectPatientId.current !== projectPatientId) {
      resetCreateCode();
      previousProjectPatientId.current = projectPatientId;
    }
  }, [projectPatientId, resetCreateCode]);

  const revoke = useMutation({
    mutationFn: async () => apiClient.post(`/studies/project-patients/${projectPatientId}/revoke-binding/`),
    onSuccess: () => {
      createCode.reset();
      return queryClient.invalidateQueries({ queryKey });
    },
  });

  const status = statusQuery.data;
  const canRevoke = Boolean(status?.has_active_session || status?.has_active_binding_code);
  const generatedCode = createCode.data?.projectPatientId === projectPatientId ? createCode.data : null;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Text strong>患者绑定信息</Typography.Text>
        <Space data-testid="patient-binding-actions" wrap>
          <Button aria-label="生成绑定码" icon={<KeyOutlined />} onClick={() => createCode.mutate(projectPatientId)} loading={createCode.isPending}>
            生成临时绑定码
          </Button>
          <WearableBindingActions />
          <Button aria-label="撤销绑定" danger icon={<DisconnectOutlined />} disabled={!canRevoke} onClick={() => revoke.mutate()} loading={revoke.isPending}>
            撤销绑定
          </Button>
        </Space>
      </Space>

      <PatientBindingDescriptions status={status} />

      {generatedCode ? (
        <Alert
          type="success"
          showIcon
          message="绑定码只显示一次"
          description={
            <Space direction="vertical">
              <Typography.Text copyable strong style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 28, letterSpacing: 8 }}>
                {generatedCode.code}
              </Typography.Text>
              <span>15 分钟内有效，请提供给患者。</span>
              <span>过期时间：{formatTime(generatedCode.expires_at)}</span>
            </Space>
          }
        />
      ) : null}
      {createCode.isError ? <Alert type="error" showIcon message="绑定码生成失败" /> : null}
      {revoke.isError ? <Alert type="error" showIcon message="撤销绑定失败" /> : null}
      {statusQuery.isError ? <Alert type="error" showIcon message="绑定状态加载失败" /> : null}
      <WearableBindingFeedback />
      <WearableBindingModals />
    </Space>
  );
}

export function ProjectPatientBindingCard({ projectPatientId }: { projectPatientId: number }) {
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Title level={5} style={{ margin: 0 }}>
        患者接入
      </Typography.Title>
      <WearableBindingProvider projectPatientId={projectPatientId}>
        <MiniappBindingSection projectPatientId={projectPatientId} />
      </WearableBindingProvider>
    </Space>
  );
}
