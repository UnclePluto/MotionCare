import { useQuery } from "@tanstack/react-query";
import { Button, Card, Input, Space, Table } from "antd";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import type { TrainingTrackingPatientSummary, TrainingTrackingPatientsResponse } from "./types";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";

  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) return value;
  return `${match[1]} ${match[2]}`;
}

function unwrapRows(data: TrainingTrackingPatientsResponse): TrainingTrackingPatientSummary[] {
  return Array.isArray(data) ? data : data.results;
}

export function TrainingTrackingPage() {
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");

  const { data = [], isLoading } = useQuery({
    queryKey: ["training-tracking", "patients", query],
    queryFn: async () => {
      const response = await apiClient.get<TrainingTrackingPatientsResponse>("/training/tracking/patients/", {
        params: { q: query.trim() },
      });
      return unwrapRows(response.data);
    },
  });

  return (
    <Card title="患者训练追踪">
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

      <Table<TrainingTrackingPatientSummary>
        rowKey="patient_id"
        loading={isLoading}
        dataSource={data}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        columns={[
          { title: "患者", dataIndex: "patient_name" },
          { title: "手机号", dataIndex: "patient_phone" },
          { title: "参与项目数", dataIndex: "project_count" },
          {
            title: "最近训练",
            dataIndex: "latest_training_at",
            render: (value: string | null) => formatDateTime(value),
          },
          { title: "近 30 天完成次数", dataIndex: "completed_count_30d" },
          {
            title: "操作",
            render: (_: unknown, row) => (
              <Link to={`/training-tracking/patients/${row.patient_id}`}>查看追踪</Link>
            ),
          },
        ]}
      />
    </Card>
  );
}
