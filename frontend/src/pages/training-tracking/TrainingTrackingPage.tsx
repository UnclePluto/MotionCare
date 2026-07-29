import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Input, Space, Table } from "antd";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import type { TrackingPatientRow } from "./types";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";

  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) return value;
  return `${match[1]} ${match[2]}`;
}

function errorMessage(error: unknown) {
  if (error && typeof error === "object" && "response" in error) {
    const data = (error as { response?: { data?: unknown } }).response?.data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  }
  return "加载训练与健康数据失败";
}

export function TrainingTrackingPage() {
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["training-tracking", "patients", query],
    queryFn: async () => {
      const response = await apiClient.get<TrackingPatientRow[]>("/training/tracking/patients/", {
        params: { q: query.trim() },
      });
      return response.data;
    },
  });

  return (
    <Card title="患者训练与健康">
      <Space wrap style={{ marginBottom: 16 }} align="center">
        <Input
          allowClear
          placeholder="患者姓名或手机号"
          style={{ width: 240 }}
          value={draftQuery}
          onChange={(event) => setDraftQuery(event.target.value)}
          onPressEnter={() => setQuery(draftQuery)}
        />
        <Button type="primary" aria-label="查询" onClick={() => setQuery(draftQuery)}>
          查询
        </Button>
      </Space>

      {isError && <Alert type="error" showIcon message={errorMessage(error)} style={{ marginBottom: 16 }} />}

      <Table<TrackingPatientRow>
        rowKey={(row) => row.patient.id}
        loading={isLoading}
        dataSource={data ?? []}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        columns={[
          {
            title: "患者",
            render: (_: unknown, row) => row.patient.name,
          },
          {
            title: "手机号",
            render: (_: unknown, row) => row.patient.phone_masked,
          },
          { title: "参与项目数", dataIndex: "project_count" },
          {
            title: "最近训练",
            dataIndex: "last_training_at",
            render: (value: string | null) => formatDateTime(value),
          },
          { title: "近 30 天完成次数", dataIndex: "last_30_days_completed_count" },
          {
            title: "设备绑定",
            render: (_: unknown, row) => row.wearable?.device_short_code ?? "未绑定",
          },
          {
            title: "最近健康同步",
            render: (_: unknown, row) => formatDateTime(row.wearable?.last_sync_at),
          },
          {
            title: "近 30 天数据完整率",
            render: (_: unknown, row) => {
              const value = row.wearable?.last_30_days_data_completeness;
              return value == null ? "—" : `${value}%`;
            },
          },
          {
            title: "操作",
            render: (_: unknown, row) => (
              <Link to={`/training-tracking/patients/${row.patient.id}`}>查看训练与健康</Link>
            ),
          },
        ]}
      />
    </Card>
  );
}
