import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Card, Descriptions, Space, Tabs, Tag } from "antd";
import { useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { VisitFormContent } from "../visits/VisitFormContent";
import { ProjectPatientBindingCard } from "./ProjectPatientBindingCard";

type VisitType = "T0" | "T1" | "T2";

type VisitSummary = {
  id: number;
  status: "draft" | "completed";
  visit_date: string | null;
};

type ProjectPatientDetail = {
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
  visit_ids?: Partial<Record<VisitType, number>>;
  visit_summaries?: Partial<Record<VisitType, VisitSummary>>;
};

const VISIT_TYPES: VisitType[] = ["T0", "T1", "T2"];

function isVisitType(v: string | null): v is VisitType {
  return v === "T0" || v === "T1" || v === "T2";
}

function visitStatusLabel(summary: VisitSummary | undefined): string {
  if (!summary) return "访视未生成";
  return summary.status === "completed" ? "已完成" : "草稿";
}

function visitDateLabel(summary: VisitSummary | undefined): string {
  if (!summary) return "未生成";
  return summary.visit_date ?? "未填写日期";
}

function firstOpenVisit(row: ProjectPatientDetail): VisitType {
  for (const vt of VISIT_TYPES) {
    if (row.visit_summaries?.[vt]?.status !== "completed") return vt;
  }
  return "T0";
}

export function ProjectPatientResearchEntryPage() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  const id = Number(projectPatientId);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["project-patient", id],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientDetail>(`/studies/project-patients/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const activeVisit = useMemo<VisitType>(() => {
    const requested = searchParams.get("visit");
    if (isVisitType(requested)) return requested;
    return data ? firstOpenVisit(data) : "T0";
  }, [data, searchParams]);

  const refreshProjectPatient = async () => {
    await qc.invalidateQueries({ queryKey: ["project-patient", id] });
  };

  if (!Number.isFinite(id)) return <Alert type="error" message="无效的项目患者 ID" />;
  if (isError) return <Alert type="error" message="记录不存在或无权限访问" />;

  const items = VISIT_TYPES.map((vt) => {
    const summary = data?.visit_summaries?.[vt];
    const visitId = summary?.id ?? data?.visit_ids?.[vt];
    return {
      key: vt,
      label: (
        <Space>
          <span>{vt}</span>
          <Tag color={summary?.status === "completed" ? "green" : summary ? "default" : "red"}>
            {visitStatusLabel(summary)}
          </Tag>
          <span>{visitDateLabel(summary)}</span>
        </Space>
      ),
      children: visitId ? (
        <VisitFormContent
          key={visitId}
          visitId={visitId}
          patientId={data?.patient}
          title={`${vt} 访视录入`}
          onVisitChanged={refreshProjectPatient}
        />
      ) : (
        <Alert type="warning" showIcon message={`${vt} 访视未生成`} />
      ),
    };
  });

  return (
    <Card
      loading={isLoading}
      title={data ? `${data.patient_name} · ${data.project_name}` : "研究录入"}
      extra={
        data ? (
          <Space wrap>
            <Link to={`/patients/${data.patient}/crf-baseline`}>基线资料</Link>
            <Link to={`/crf?projectPatientId=${data.id}`}>打开 CRF</Link>
          </Space>
        ) : null
      }
    >
      {data && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="患者">{data.patient_name}</Descriptions.Item>
            <Descriptions.Item label="项目">{data.project_name}</Descriptions.Item>
            <Descriptions.Item label="分组">{data.group_name ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="入组时间">{data.enrolled_at || "—"}</Descriptions.Item>
          </Descriptions>
          <ProjectPatientBindingCard projectPatientId={data.id} />
          <Tabs
            destroyOnHidden
            activeKey={activeVisit}
            onChange={(key) => navigate(`/research-entry/project-patients/${id}?visit=${key}`)}
            items={items}
          />
        </Space>
      )}
    </Card>
  );
}
