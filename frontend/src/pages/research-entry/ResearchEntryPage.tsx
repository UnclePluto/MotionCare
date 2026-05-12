import { useQuery } from "@tanstack/react-query";
import { Button, Card, Input, Select, Space, Table, Tag } from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type StudyProject = { id: number; name: string };

type VisitRow = {
  id: number;
  project_patient: number;
  visit_type: string;
  status: string;
  visit_date: string | null;
  patient_id: number;
  patient_name: string;
  patient_phone: string;
  project_id: number;
  project_name: string;
};

type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export function ResearchEntryPage() {
  const [page, setPage] = useState(1);
  const [visitType, setVisitType] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
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
    const p: Record<string, string | number> = { page };
    if (visitType) p.visit_type = visitType;
    if (status) p.status = status;
    if (projectId) p.project = projectId;
    if (patientNameQuery.trim()) p.patient_name = patientNameQuery.trim();
    return p;
  }, [page, visitType, status, projectId, patientNameQuery]);

  const { data, isLoading } = useQuery({
    queryKey: ["visits", "research-entry", queryParams],
    queryFn: async () => {
      const r = await apiClient.get<Paginated<VisitRow>>("/visits/", { params: queryParams });
      return r.data;
    },
  });

  const rows = data?.results ?? [];

  return (
    <Card title="研究录入">
      <Space wrap style={{ marginBottom: 16 }} align="center">
        <span>访视类型</span>
        <Select
          allowClear
          placeholder="全部"
          style={{ width: 120 }}
          value={visitType}
          onChange={(v) => {
            setVisitType(v);
            setPage(1);
          }}
          options={[
            { value: "T0", label: "T0" },
            { value: "T1", label: "T1" },
            { value: "T2", label: "T2" },
          ]}
        />
        <span>状态</span>
        <Select
          allowClear
          placeholder="全部"
          style={{ width: 120 }}
          value={status}
          onChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
          options={[
            { value: "draft", label: "草稿" },
            { value: "completed", label: "已完成" },
          ]}
        />
        <span>项目</span>
        <Select
          allowClear
          placeholder="全部"
          style={{ width: 200 }}
          value={projectId}
          onChange={(v) => {
            setProjectId(v);
            setPage(1);
          }}
          options={projects.map((p) => ({ value: p.id, label: p.name }))}
        />
        <span>患者姓名</span>
        <Input
          allowClear
          style={{ width: 160 }}
          value={patientNameDraft}
          onChange={(e) => setPatientNameDraft(e.target.value)}
          onPressEnter={() => {
            setPatientNameQuery(patientNameDraft);
            setPage(1);
          }}
        />
        <Button
          type="primary"
          onClick={() => {
            setPatientNameQuery(patientNameDraft);
            setPage(1);
          }}
        >
          查询
        </Button>
      </Space>

      <Table<VisitRow>
        rowKey="id"
        loading={isLoading}
        dataSource={rows}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.count ?? 0,
          onChange: (p) => setPage(p),
          showSizeChanger: false,
        }}
        columns={[
          {
            title: "患者",
            dataIndex: "patient_name",
            render: (t: string, r: VisitRow) => (
              <>
                {t} · {r.patient_phone}
              </>
            ),
          },
          { title: "项目", dataIndex: "project_name" },
          {
            title: "访视",
            render: (_: unknown, r: VisitRow) => (
              <Space>
                <Tag>{r.visit_type}</Tag>
                {r.visit_date ?? "—"}
              </Space>
            ),
          },
          {
            title: "状态",
            dataIndex: "status",
            render: (s: string) => (
              <Tag color={s === "completed" ? "green" : "default"}>
                {s === "completed" ? "已完成" : "草稿"}
              </Tag>
            ),
          },
          {
            title: "操作",
            render: (_: unknown, r: VisitRow) => (
              <Space>
                <Link to={`/visits/${r.id}`}>访视表单</Link>
                <Link to={`/patients/${r.patient_id}/crf-baseline`}>CRF 基线</Link>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
