import { useQuery } from "@tanstack/react-query";
import { Button, Card, Input, Select, Space, Table, Tag } from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type StudyProject = { id: number; name: string };
type VisitType = "T0" | "T1" | "T2";
type VisitSummary = { id: number; status: "draft" | "completed"; visit_date: string | null };

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
  visit_summaries?: Partial<Record<VisitType, VisitSummary>>;
};

const VISIT_TYPES: VisitType[] = ["T0", "T1", "T2"];

function statusTag(summary: VisitSummary | undefined) {
  if (!summary) return <Tag color="red">访视未生成</Tag>;
  return (
    <Tag color={summary.status === "completed" ? "green" : "default"}>
      {summary.status === "completed" ? "已完成" : "草稿"}
      {summary.visit_date ? ` · ${summary.visit_date}` : ""}
    </Tag>
  );
}

export function ResearchEntryPage() {
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
    if (patientNameQuery.trim()) p.patient_name = patientNameQuery.trim();
    return p;
  }, [projectId, patientNameQuery]);

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["project-patients", "research-entry", queryParams],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>("/studies/project-patients/", { params: queryParams });
      return r.data;
    },
  });

  return (
    <Card title="研究录入">
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
            title: "T0 / T1 / T2",
            render: (_: unknown, r) => (
              <Space wrap>
                {VISIT_TYPES.map((vt) => (
                  <Link key={vt} to={`/research-entry/project-patients/${r.id}?visit=${vt}`}>
                    {vt} {statusTag(r.visit_summaries?.[vt])}
                  </Link>
                ))}
              </Space>
            ),
          },
          {
            title: "操作",
            render: (_: unknown, r) => (
              <Space>
                <Link to={`/research-entry/project-patients/${r.id}`}>录入</Link>
                <Link to={`/patients/${r.patient}/crf-baseline`}>基线资料</Link>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
