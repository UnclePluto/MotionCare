import { useQuery } from "@tanstack/react-query";
import { Button, Card, Input, Select, Space, Table } from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type StudyProject = { id: number; name: string };

type ProjectPatientRow = {
  id: number;
  project: number;
  project_name: string;
  project_status: "draft" | "active" | "archived";
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string;
  updated_at: string;
};

const PROJECT_STATUS_LABEL: Record<ProjectPatientRow["project_status"], string> = {
  draft: "草稿",
  active: "进行中",
  archived: "已完结",
};

function patientSearchParams(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return {};

  const normalizedPhone = trimmed.replace(/[\s-]+/g, "");
  if (/^\d+$/.test(normalizedPhone)) return { patient_phone: normalizedPhone };

  return { patient_name: trimmed };
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";

  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) return value;

  return `${match[1]} ${match[2]}`;
}

export function PrescriptionEntryPage() {
  const [projectId, setProjectId] = useState<number | undefined>();
  const [patientNameDraft, setPatientNameDraft] = useState("");
  const [patientNameQuery, setPatientNameQuery] = useState("");

  const { data: projects = [] } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
  });

  const queryParams = useMemo(() => {
    const p: Record<string, string | number> = {};
    if (projectId) p.project = projectId;
    Object.assign(p, patientSearchParams(patientNameQuery));
    return p;
  }, [projectId, patientNameQuery]);

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["project-patients", "prescriptions", queryParams],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>("/studies/project-patients/", { params: queryParams });
      return r.data;
    },
  });

  return (
    <Card title="处方管理">
      <Space wrap style={{ marginBottom: 16 }} align="center">
        <span>项目</span>
        <Select
          allowClear
          placeholder="全部"
          style={{ width: 220 }}
          value={projectId}
          onChange={setProjectId}
          options={projects.map((p) => ({ value: p.id, label: p.name }))}
        />
        <span>患者</span>
        <Input
          allowClear
          placeholder="患者姓名或手机号"
          style={{ width: 180 }}
          value={patientNameDraft}
          onChange={(e) => setPatientNameDraft(e.target.value)}
          onPressEnter={() => setPatientNameQuery(patientNameDraft)}
        />
        <Button type="primary" aria-label="查询" onClick={() => setPatientNameQuery(patientNameDraft)}>
          查询
        </Button>
      </Space>

      <Table<ProjectPatientRow>
        rowKey="id"
        loading={isLoading}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        columns={[
          {
            title: "患者",
            dataIndex: "patient_name",
            render: (t: string, r) => (
              <>
                <span>{t}</span> · {r.patient_phone}
              </>
            ),
          },
          { title: "项目", dataIndex: "project_name" },
          {
            title: "分组",
            dataIndex: "group_name",
            render: (v: string | null) => v ?? "—",
          },
          {
            title: "项目状态",
            dataIndex: "project_status",
            render: (v: ProjectPatientRow["project_status"]) => PROJECT_STATUS_LABEL[v] ?? v,
          },
          {
            title: "入组时间",
            dataIndex: "enrolled_at",
            render: (v: string | null | undefined) => formatDateTime(v),
          },
          {
            title: "操作",
            render: (_: unknown, r) => (
              <Space>
                <Link to={`/prescriptions/project-patients/${r.id}`}>处方</Link>
                <Link to={`/patient-sim/project-patients/${r.id}`}>跟练模拟</Link>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
