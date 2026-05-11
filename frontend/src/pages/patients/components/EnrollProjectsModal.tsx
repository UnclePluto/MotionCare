import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal, Select, Space, Table, Typography, message } from "antd";
import { isAxiosError } from "axios";
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../../../api/client";

type StudyProject = { id: number; name: string };

type StudyGroupRow = {
  id: number;
  project: number;
  name: string;
  is_active: boolean;
};

type ProjectPatientRow = { project: number };

type EnrollResponse = {
  detail: string;
  created: { project_id: number; group_id: number; project_patient_id: number }[];
};

type Props = {
  open: boolean;
  onClose: () => void;
  patientId: number;
};

export function EnrollProjectsModal({ open, onClose, patientId }: Props) {
  const qc = useQueryClient();
  const [groupByProject, setGroupByProject] = useState<Record<number, number | undefined>>({});

  useEffect(() => {
    if (open) setGroupByProject({});
  }, [open]);

  const { data: projects = [] } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
    enabled: open,
  });

  const { data: allGroups = [] } = useQuery({
    queryKey: ["study-groups", "all-active"],
    queryFn: async () => {
      const r = await apiClient.get<StudyGroupRow[]>("/studies/groups/");
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
  const availableProjects = useMemo(
    () => projects.filter((p) => !enrolledIds.has(p.id)),
    [projects, enrolledIds],
  );
  const groupsByProject = useMemo(() => {
    const map: Record<number, StudyGroupRow[]> = {};
    for (const g of allGroups) {
      if (!g.is_active) continue;
      (map[g.project] ||= []).push(g);
    }
    return map;
  }, [allGroups]);

  const enrollMutation = useMutation({
    mutationFn: async (
      enrollments: { project_id: number; group_id: number }[],
    ) => {
      const r = await apiClient.post<EnrollResponse>(`/patients/${patientId}/enroll-projects/`, {
        enrollments,
      });
      return r.data;
    },
    onSuccess: async (data) => {
      message.success(`已确认入组 ${data.created.length} 个项目。`);
      await qc.invalidateQueries({ queryKey: ["project-patients", "patient", patientId] });
      await qc.invalidateQueries({ queryKey: ["patient", String(patientId)] });
      await qc.invalidateQueries({ queryKey: ["project-patients"] });
      onClose();
    },
    onError: (err: unknown) => {
      if (!isAxiosError(err)) {
        message.error("入组失败");
        return;
      }
      const d = err.response?.data;
      if (d && typeof d === "object" && "detail" in d) {
        const detail = (d as { detail?: unknown }).detail;
        if (typeof detail === "string") {
          message.error(detail);
          return;
        }
      }
      message.error("入组失败");
    },
  });

  const handleOk = () => {
    const enrollments = availableProjects
      .map((p) => ({ project_id: p.id, group_id: groupByProject[p.id] }))
      .filter((e): e is { project_id: number; group_id: number } => typeof e.group_id === "number");
    if (!enrollments.length) {
      message.warning("请至少为一个项目选择分组。");
      return;
    }
    enrollMutation.mutate(enrollments);
  };

  return (
    <Modal
      title="直接确认入组到分组"
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      okText="确认入组"
      confirmLoading={enrollMutation.isPending}
      destroyOnClose
      width={640}
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          为患者选择项目下的目标分组并确认入组。提交后该分组关系将直接生效，无需再进入项目看板随机。
        </Typography.Paragraph>
        <Table<StudyProject>
          rowKey="id"
          size="small"
          dataSource={availableProjects}
          pagination={false}
          columns={[
            { title: "项目名称", dataIndex: "name" },
            {
              title: "分组",
              key: "group",
              render: (_: unknown, row) => {
                const opts = (groupsByProject[row.id] ?? []).map((g) => ({
                  value: g.id,
                  label: g.name,
                }));
                return (
                  <Select
                    style={{ width: 200 }}
                    placeholder="选择分组"
                    options={opts}
                    value={groupByProject[row.id]}
                    onChange={(v) =>
                      setGroupByProject((prev) => ({ ...prev, [row.id]: v as number | undefined }))
                    }
                  />
                );
              },
            },
          ]}
        />
      </Space>
    </Modal>
  );
}
