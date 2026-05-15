import { DisconnectOutlined, KeyOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Space, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useEffect, useRef } from "react";

import { apiClient } from "../../api/client";

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

export function ProjectPatientBindingCard({ projectPatientId }: { projectPatientId: number }) {
  const queryClient = useQueryClient();
  const queryKey = ["project-patient-binding-status", projectPatientId];

  const statusQuery = useQuery({
    queryKey,
    queryFn: async () => {
      const response = await apiClient.get<BindingStatus>(
        `/studies/project-patients/${projectPatientId}/binding-status/`,
      );
      return response.data;
    },
  });

  const createCode = useMutation({
    mutationFn: async (targetProjectPatientId: number): Promise<BindingCodeDisplay> => {
      const response = await apiClient.post<BindingCodeResponse>(
        `/studies/project-patients/${targetProjectPatientId}/binding-code/`,
      );
      return { ...response.data, projectPatientId: targetProjectPatientId };
    },
    onSuccess: (_data, targetProjectPatientId) =>
      queryClient.invalidateQueries({
        queryKey: ["project-patient-binding-status", targetProjectPatientId],
      }),
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
    mutationFn: async () => {
      await apiClient.post(`/studies/project-patients/${projectPatientId}/revoke-binding/`);
    },
    onSuccess: () => {
      createCode.reset();
      return queryClient.invalidateQueries({ queryKey });
    },
  });

  const status = statusQuery.data;
  const canRevoke = Boolean(status?.has_active_session || status?.has_active_binding_code);
  const generatedCode =
    createCode.data?.projectPatientId === projectPatientId ? createCode.data : null;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={5} style={{ margin: 0 }}>
          小程序绑定
        </Typography.Title>
        <Space wrap>
          <Button
            aria-label="生成绑定码"
            icon={<KeyOutlined />}
            onClick={() => createCode.mutate(projectPatientId)}
            loading={createCode.isPending}
          >
            生成绑定码
          </Button>
          <Button
            aria-label="撤销绑定"
            danger
            icon={<DisconnectOutlined />}
            disabled={!canRevoke}
            onClick={() => revoke.mutate()}
            loading={revoke.isPending}
          >
            撤销绑定
          </Button>
        </Space>
      </Space>

      <Descriptions size="small" bordered column={3}>
        <Descriptions.Item label="绑定状态">
          {status?.has_active_session ? <Tag color="green">已绑定</Tag> : <Tag>未绑定</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="有效绑定码">
          {status?.has_active_binding_code ? <Tag color="blue">存在</Tag> : <Tag>无</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="最近绑定时间">
          {formatTime(status?.last_bound_at)}
        </Descriptions.Item>
        <Descriptions.Item label="绑定码过期时间">
          {formatTime(status?.binding_code_expires_at)}
        </Descriptions.Item>
        <Descriptions.Item label="登录过期时间">
          {formatTime(status?.active_session_expires_at)}
        </Descriptions.Item>
      </Descriptions>

      {generatedCode && (
        <Alert
          type="success"
          showIcon
          message="绑定码只显示一次"
          description={
            <Space direction="vertical">
              <Typography.Text
                copyable
                strong
                style={{
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: 28,
                  letterSpacing: 8,
                }}
              >
                {generatedCode.code}
              </Typography.Text>
              <span>15 分钟内有效，请提供给患者。</span>
              <span>过期时间：{formatTime(generatedCode.expires_at)}</span>
            </Space>
          }
        />
      )}

      {createCode.isError && <Alert type="error" showIcon message="绑定码生成失败" />}
      {revoke.isError && <Alert type="error" showIcon message="撤销绑定失败" />}
      {statusQuery.isError && <Alert type="error" showIcon message="绑定状态加载失败" />}
    </Space>
  );
}
