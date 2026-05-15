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
  message,
} from "antd";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "../../api/client";

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
  visits: Record<string, { visit_date: string; status: string; form_data: unknown }>;
  missing_fields: string[];
};

type ProjectPatientOption = {
  id: number;
  patient_name: string;
  patient_phone: string;
};

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

  const exportMutation = useMutation({
    mutationFn: async () => {
      if (!activeId) return;
      const r = await apiClient.post<{ docx_file?: string | null }>(
        `/crf/project-patients/${activeId}/export/`,
        {},
      );
      return r.data;
    },
    onSuccess: (data) => {
      message.success("导出任务已完成");
      if (data?.docx_file) {
        window.open(data.docx_file, "_blank", "noopener,noreferrer");
      }
      void qc.invalidateQueries({ queryKey: ["crf-preview", activeId] });
    },
    onError: () => message.error("导出失败（请确认模板文件存在且服务可写 media 目录）"),
  });

  const onChangeProjectPatient = (id: number | undefined) => {
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
          <Alert
            type="info"
            showIcon
            message="第一版允许带缺失字段导出。缺失字段在预览中提示，导出文件中留空。"
          />
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
              {preview.project.crf_template_version}
            </Descriptions.Item>
            <Descriptions.Item label="分组">{preview.group.name || "—"}</Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card title="访视节点">
        {preview &&
          Object.entries(preview.visits).map(([k, v]) => (
            <Card key={k} type="inner" title={k} style={{ marginBottom: 12 }}>
              <Typography.Text type="secondary">
                访视日期：{v.visit_date || "—"} · 状态：{v.status}
              </Typography.Text>
            </Card>
          ))}
      </Card>

      <Card title="缺失字段">
        <List
          dataSource={preview?.missing_fields ?? []}
          locale={{ emptyText: activeId ? "暂无缺失字段" : "未选择项目患者" }}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>

      <Space>
        <Button
          type="primary"
          disabled={!activeId}
          loading={exportMutation.isPending}
          onClick={() => exportMutation.mutate()}
        >
          导出 DOCX
        </Button>
        <Typography.Text type="secondary">
          PDF 导出后续接入；当前导出文件由后端写入 media 目录并返回链接。
        </Typography.Text>
      </Space>
    </Space>
  );
}
