import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Drawer, Empty, Popconfirm, Space, Table, Tabs, Tag, message } from "antd";
import { useState } from "react";

import { apiClient } from "../../api/client";
import { FixedActionLibraryTab } from "./FixedActionLibraryTab";
import { PrescriptionDrawer } from "./PrescriptionDrawer";
import { weeklyFrequencyLabel } from "./prescriptionUtils";
import type { ActionLibraryItem, Prescription, PrescriptionAction } from "./types";

type Props = {
  projectPatientId: number;
};

function formatDateTime(value: string | null | undefined) {
  return value ? value.replace("T", " ").slice(0, 16) : "—";
}

function normalizeCurrentPrescription(data: Prescription | null | "" | undefined): Prescription | null {
  if (!data || typeof data !== "object") return null;
  return data;
}

const STATUS_LABEL: Record<Prescription["status"], string> = {
  draft: "草稿",
  active: "生效中",
  pending: "待生效",
  archived: "已归档",
  terminated: "已终止",
};

function PrescriptionActionTable({ actions }: { actions: PrescriptionAction[] }) {
  return (
    <Table<PrescriptionAction>
      rowKey="id"
      pagination={false}
      size="small"
      dataSource={actions}
      columns={[
        { title: "动作", dataIndex: "action_name_snapshot" },
        { title: "类型", dataIndex: "action_type_snapshot" },
        { title: "频次", dataIndex: "weekly_frequency", render: (value: string) => weeklyFrequencyLabel(value) },
        {
          title: "时长",
          dataIndex: "duration_minutes",
          render: (value: number | null) => (value ? `${value} 分钟` : "—"),
        },
      ]}
    />
  );
}

export function PrescriptionPanel({ projectPatientId }: Props) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [selectedHistory, setSelectedHistory] = useState<Prescription | null>(null);
  const queryClient = useQueryClient();

  const currentQuery = useQuery({
    queryKey: ["current-prescription", projectPatientId],
    queryFn: async () => {
      const response = await apiClient.get<Prescription | null>("/prescriptions/current/", {
        params: { project_patient: projectPatientId },
      });
      return normalizeCurrentPrescription(response.data);
    },
  });

  const historyQuery = useQuery({
    queryKey: ["prescription-history", projectPatientId],
    queryFn: async () => {
      const response = await apiClient.get<Prescription[]>("/prescriptions/", {
        params: { project_patient: projectPatientId, include_terminated: "true" },
      });
      return response.data;
    },
  });

  const actionsQuery = useQuery({
    queryKey: ["action-library"],
    queryFn: async () => {
      const response = await apiClient.get<ActionLibraryItem[]>("/prescriptions/actions/");
      return response.data;
    },
  });

  const activateMutation = useMutation({
    mutationFn: async (payload: unknown) => {
      const response = await apiClient.post<Prescription>(
        `/studies/project-patients/${projectPatientId}/prescriptions/activate-now/`,
        payload,
      );
      return response.data;
    },
    onSuccess: async () => {
      message.success("处方已生效");
      setDrawerOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["current-prescription", projectPatientId] }),
        queryClient.invalidateQueries({ queryKey: ["prescription-history", projectPatientId] }),
      ]);
    },
  });

  const terminateMutation = useMutation({
    mutationFn: async (prescriptionId: number) => {
      const response = await apiClient.post<Prescription>(`/prescriptions/${prescriptionId}/terminate/`);
      return response.data;
    },
    onSuccess: async () => {
      message.success("处方已终止");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["current-prescription", projectPatientId] }),
        queryClient.invalidateQueries({ queryKey: ["prescription-history", projectPatientId] }),
      ]);
    },
  });

  const current = currentQuery.data ?? null;
  const actions = actionsQuery.data ?? [];
  const history = (historyQuery.data ?? []).filter((item) => item.status !== "active");

  return (
    <Card
      title="处方管理"
      extra={
        <Space wrap>
          <Button onClick={() => setHistoryOpen(true)}>历史处方</Button>
          {current ? (
            <Popconfirm
              title="确认终止当前处方？"
              description="终止后患者端将无法继续按该处方提交训练。"
              okText="确认终止"
              cancelText="取消"
              onConfirm={() => terminateMutation.mutate(current.id)}
            >
              <Button danger loading={terminateMutation.isPending}>
                终止处方
              </Button>
            </Popconfirm>
          ) : null}
          <Button type="primary" onClick={() => setDrawerOpen(true)}>
            {current ? "调整处方" : "开具处方"}
          </Button>
        </Space>
      }
    >
      <Tabs
        items={[
          {
            key: "prescription",
            label: "处方管理",
            children: (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                {!current ? (
                  <Alert type="info" showIcon message="当前暂无生效处方。" />
                ) : (
                  <Alert type="success" showIcon message={`当前生效处方 v${current.version}`} />
                )}
                {current ? (
                  <>
                    <Descriptions size="small" bordered column={2}>
                      <Descriptions.Item label="版本">v{current.version}</Descriptions.Item>
                      <Descriptions.Item label="开设医生">{current.opened_by_name}</Descriptions.Item>
                      <Descriptions.Item label="创建时间">{formatDateTime(current.opened_at)}</Descriptions.Item>
                      <Descriptions.Item label="生效时间">{formatDateTime(current.effective_at)}</Descriptions.Item>
                    </Descriptions>
                    <PrescriptionActionTable actions={current.actions} />
                  </>
                ) : null}
              </Space>
            ),
          },
          {
            key: "actions",
            label: "固定动作库",
            children: <FixedActionLibraryTab actions={actions} />,
          },
        ]}
      />
      <PrescriptionDrawer
        open={drawerOpen}
        actions={actions}
        currentPrescription={current}
        submitting={activateMutation.isPending}
        onClose={() => setDrawerOpen(false)}
        onSubmit={(payload) => activateMutation.mutate(payload)}
      />
      <Drawer
        title={selectedHistory ? `历史处方 v${selectedHistory.version}` : "历史处方"}
        open={historyOpen}
        width={920}
        onClose={() => {
          setHistoryOpen(false);
          setSelectedHistory(null);
        }}
      >
        {selectedHistory ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Button onClick={() => setSelectedHistory(null)}>返回版本列表</Button>
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="版本">v{selectedHistory.version}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag>{STATUS_LABEL[selectedHistory.status]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="开设医生">{selectedHistory.opened_by_name}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(selectedHistory.opened_at)}</Descriptions.Item>
              <Descriptions.Item label="归档时间">{formatDateTime(selectedHistory.archived_at)}</Descriptions.Item>
              <Descriptions.Item label="生效时间">{formatDateTime(selectedHistory.effective_at)}</Descriptions.Item>
            </Descriptions>
            <PrescriptionActionTable actions={selectedHistory.actions} />
          </Space>
        ) : (
          <Table<Prescription>
            rowKey="id"
            loading={historyQuery.isLoading}
            dataSource={history}
            locale={{ emptyText: <Empty description="暂无历史处方" /> }}
            onRow={(record) => ({
              onClick: () => setSelectedHistory(record),
              style: { cursor: "pointer" },
            })}
            columns={[
              { title: "版本号", dataIndex: "version", render: (value: number) => `v${value}` },
              { title: "状态", dataIndex: "status", render: (value: Prescription["status"]) => <Tag>{STATUS_LABEL[value]}</Tag> },
              { title: "开设医生", dataIndex: "opened_by_name" },
              { title: "创建时间", dataIndex: "opened_at", render: (value: string) => formatDateTime(value) },
              { title: "归档时间", dataIndex: "archived_at", render: (value: string | null) => formatDateTime(value) },
            ]}
          />
        )}
      </Drawer>
    </Card>
  );
}
