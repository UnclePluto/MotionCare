import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  List,
  Select,
  Space,
  Typography,
} from "antd";
import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { formatCrfDateForReview } from "../../crf/fieldState";
import { apiClient } from "../../api/client";
import { CrfReadOnlySections, type CrfReadOnlySection, type CrfProjectionIssue } from "../../crf/components/CrfReadOnlySections";

type CrfPreviewPayload = {
  project_patient_id: number;
  patient: { name: string; gender: string; age: number | null; phone: string };
  patient_baseline?: {
    subject_id: string;
    name_initials: string;
    demographics: Record<string, unknown>;
  };
  project: { name: string; crf_template_version: string };
  group: { name: string };
  visits: Record<string, { visit_date: string | null; status: string; form_data: unknown }>;
  missing_fields: string[];
  sections?: CrfReadOnlySection[];
  issues?: CrfProjectionIssue[];
  counts?: { normal: number; unknown: number; not_applicable: number; unresolved: number };
  template_revision?: string;
};

type ProjectPatientOption = {
  id: number;
  patient_name: string;
  patient_phone: string;
};

function visitDateSummary(sections: CrfReadOnlySection[] | undefined, scope: string, native: string | null): string {
  const field=sections?.filter(section=>section.scope === scope && !section.supplemental).flatMap(section=>section.fields).find(field=>field.storage === "visit.visit_date");
  if (!field) return native || "未填写";
  if (field.issues.length || (field.state === "unresolved" && (field.value != null || field.raw_value != null || field.partial_date_value != null))) return "需核对";
  if (field.value == null) return field.state === "unknown" ? "不详" : field.state === "not_applicable" ? "不适用" : "未填写";
  return formatCrfDateForReview({widget:"date",allow_partial_date:true},field.value) ?? (typeof field.value === "string" ? field.value : "需核对");
}

export function CrfPreviewPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const qpId = searchParams.get("projectPatientId");
  const initialId = qpId ? Number(qpId) : undefined;
  const [selectedId, setSelectedId] = useState<number | undefined>(
    Number.isFinite(initialId as number) ? initialId : undefined,
  );

  const { data: ppOptions, isLoading: loadingOptions } = useQuery({
    queryKey: ["project-patients-all"],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientOption[]>("/studies/project-patients/");
      return r.data;
    },
  });

  const selectOptions = useMemo(
    () =>
      (ppOptions ?? []).map((p) => ({
        value: p.id,
        label: `${p.patient_name}（${p.patient_phone}）`,
      })),
    [ppOptions],
  );

  const activeId = selectedId;

  const { data: preview, isLoading: loadingPreview } = useQuery({
    queryKey: ["crf-preview", activeId],
    queryFn: async () => {
      const r = await apiClient.get<CrfPreviewPayload>(
        `/crf/project-patients/${activeId}/preview/`,
      );
      return r.data;
    },
    enabled: !!activeId,
  });

  type ExportFiles = { project_patient: number; docx_file: string; pdf_file: string };
  const selection = useRef({ id: activeId, generation: 0 });
  const [exportFiles, setExportFiles] = useState<ExportFiles | null>(null);
  const [exportError, setExportError] = useState(false);
  const exportMutation = useMutation({
    mutationFn: async (target: { id: number; generation: number }) => {
      const r = await apiClient.post<ExportFiles>(
        `/crf/project-patients/${target.id}/export/`, {},
      );
      if (!r.data?.docx_file || !r.data?.pdf_file || r.data.project_patient !== target.id) {
        throw new Error("导出文件未完整生成");
      }
      return r.data;
    },
    onSuccess: (data, target) => {
      if (selection.current.id !== target.id || selection.current.generation !== target.generation) return;
      setExportFiles(data);
      setExportError(false);
      void qc.invalidateQueries({ queryKey: ["crf-preview", target.id] });
    },
    onError: (_error, target) => {
      if (selection.current.id !== target.id || selection.current.generation !== target.generation) return;
      setExportError(true);
    },
  });

  const onChangeProjectPatient = (id: number | undefined) => {
    selection.current = { id, generation: selection.current.generation + 1 };
    setExportFiles(null);
    setExportError(false);
    exportMutation.reset();
    setSelectedId(id);
    if (id) {
      setSearchParams({ projectPatientId: String(id) });
    } else {
      setSearchParams({});
    }
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title="CRF 预览">
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <Space wrap align="center">
            <Typography.Text>项目患者：</Typography.Text>
            <Select
              style={{ minWidth: 360 }}
              placeholder="选择项目患者记录"
              loading={loadingOptions}
              options={selectOptions}
              value={activeId}
              onChange={(v) => onChangeProjectPatient(v)}
              allowClear
              showSearch
              optionFilterProp="label"
            />
          </Space>
        </Space>
      </Card>

      <Card title="摘要" loading={loadingPreview && !!activeId}>
        {!activeId && <Typography.Text type="secondary">请先选择项目患者。</Typography.Text>}
        {preview && (
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="受试者编号">
              {preview.patient_baseline?.subject_id || "—"}
            </Descriptions.Item>
            <Descriptions.Item label="教育年限">
              {typeof preview.patient_baseline?.demographics?.["education_years"] === "number"
                ? preview.patient_baseline.demographics["education_years"]
                : "—"}
            </Descriptions.Item>
            <Descriptions.Item label="患者">{preview.patient.name}</Descriptions.Item>
            <Descriptions.Item label="手机号">{preview.patient.phone}</Descriptions.Item>
            <Descriptions.Item label="项目">{preview.project.name}</Descriptions.Item>
            <Descriptions.Item label="模板版本">
              {preview.template_revision ?? preview.project.crf_template_version}
            </Descriptions.Item>
            <Descriptions.Item label="分组">{preview.group.name || "—"}</Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card title="访视节点">
        {preview &&
          Object.entries(preview.visits).map(([k, v]) => (
            <Typography.Paragraph key={k}>
              {k} · 访视日期：{visitDateSummary(preview.sections,k,v.visit_date)} · 完成状态：{v.status === "completed" || v.status === "done" ? "已完成" : v.status ? "草稿" : "无记录"}
            </Typography.Paragraph>
          ))}
      </Card>

      <Card title="填报完整性">
        {preview?.counts && <Typography.Paragraph>
          已填 {preview.counts.normal} 项 · 不详 {preview.counts.unknown} 项 · 不适用 {preview.counts.not_applicable} 项 · 未处理 {preview.counts.unresolved} 项
        </Typography.Paragraph>}
        <List
          dataSource={preview?.missing_fields ?? []}
          locale={{ emptyText: !activeId ? "未选择项目患者" : !preview?.counts ? "完整性尚未核对" : preview.counts.unknown || preview.counts.not_applicable ? "适用项均已处理，包含不详或不适用记录" : "适用项均已填写" }}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>

      {!!preview?.issues?.length && <Alert type="warning" showIcon message="待核对记录" description={
        <List size="small" dataSource={preview.issues} renderItem={(issue) => <List.Item>{issue.scope === "patient_baseline" ? "基线资料" : issue.scope} · {issue.message}</List.Item>} />
      } />}
      {preview?.sections && <CrfReadOnlySections sections={preview.sections} />}

      <Space>
        <Button
          type="primary"
          disabled={!activeId}
          loading={exportMutation.isPending && exportMutation.variables?.id === activeId && exportMutation.variables?.generation === selection.current.generation}
          onClick={() => {
            if (!activeId) return;
            setExportFiles(null);
            setExportError(false);
            exportMutation.mutate({ id: activeId, generation: selection.current.generation });
          }}
        >
          导出 DOCX / PDF
        </Button>
        {exportFiles && <>
          <Button href={exportFiles.docx_file} target="_blank" rel="noopener noreferrer">下载 DOCX</Button>
          <Button href={exportFiles.pdf_file} target="_blank" rel="noopener noreferrer">下载 PDF</Button>
        </>}
      </Space>
      {exportError && <Alert type="error" showIcon message="导出失败，请稍后重试或联系管理员。" />}
    </Space>
  );
}
