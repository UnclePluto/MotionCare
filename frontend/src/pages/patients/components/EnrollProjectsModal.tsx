import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Checkbox, Modal, Space, Typography, message } from "antd";
import { isAxiosError } from "axios";
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../../../api/client";

type StudyProject = { id: number; name: string };

type ProjectPatientRow = { project: number };

type EnrollResponse = {
  detail: string;
  created: { project_id: number; project_patient_id: number }[];
  skipped_project_ids: number[];
};

type Props = {
  open: boolean;
  onClose: () => void;
  patientId: number;
};

export function EnrollProjectsModal({ open, onClose, patientId }: Props) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);

  useEffect(() => {
    if (open) setSelected([]);
  }, [open]);

  const { data: projects = [] } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
    enabled: open,
  });

  const { data: links = [] } = useQuery({
    queryKey: ["project-patients", "patient", patientId],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>(`/studies/project-patients/?patient=${patientId}`);
      return r.data;
    },
    enabled: open && Number.isFinite(patientId),
  });

  const enrolledIds = useMemo(() => new Set(links.map((l) => l.project)), [links]);

  const enrollMutation = useMutation({
    mutationFn: async (project_ids: number[]) => {
      const r = await apiClient.post<EnrollResponse>(`/patients/${patientId}/enroll-projects/`, {
        project_ids,
      });
      return r.data;
    },
    onSuccess: async (data) => {
      const parts = [data.detail];
      if (data.created.length) parts.push(`新关联 ${data.created.length} 个项目。`);
      if (data.skipped_project_ids.length) parts.push(`${data.skipped_project_ids.length} 个已在项目中，已跳过。`);
      message.success(parts.join(""));
      await qc.invalidateQueries({ queryKey: ["project-patients", "patient", patientId] });
      await qc.invalidateQueries({ queryKey: ["patient", String(patientId)] });
      onClose();
    },
    onError: (err: unknown) => {
      if (!isAxiosError(err)) {
        message.error("入组失败");
        return;
      }
      const d = err.response?.data;
      if (d && typeof d === "object") {
        if ("detail" in d && typeof (d as { detail?: unknown }).detail === "string") {
          message.error((d as { detail: string }).detail);
          return;
        }
        if ("project_ids" in d) {
          message.error(String((d as { project_ids: unknown }).project_ids));
          return;
        }
      }
      message.error("入组失败");
    },
  });

  const options = projects.map((p) => ({
    label: p.name,
    value: p.id,
    disabled: enrolledIds.has(p.id),
  }));

  const handleOk = () => {
    const project_ids = selected.filter((id) => !enrolledIds.has(id));
    if (!project_ids.length) {
      message.warning("请至少选择一个尚未入组的研究项目。");
      return;
    }
    enrollMutation.mutate(project_ids);
  };

  return (
    <Modal
      title="加入研究项目"
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={enrollMutation.isPending}
      destroyOnClose
      width={520}
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          加入后请到各项目的「项目详情」看板勾选患者并完成「随机分组」，系统会按各组权重（target_ratio）分配实验组。
        </Typography.Paragraph>
        <Checkbox.Group
          style={{ display: "flex", flexDirection: "column", gap: 8 }}
          options={options}
          value={selected}
          onChange={(v) => setSelected(v as number[])}
        />
      </Space>
    </Modal>
  );
}
