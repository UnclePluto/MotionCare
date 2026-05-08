import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Select,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../../api/client";

type PatientOption = { id: number; name: string; phone: string };
type StudyGroupRow = { id: number; name: string; target_ratio: number };
type ProjectPatientRow = {
  id: number;
  patient: number;
  patient_name: string;
  group: number | null;
  grouping_status: string;
};
type GroupingBatchRow = { id: number; project: number; status: string };

type Props = {
  projectId: number;
};

export function GroupingBatchPanel({ projectId }: Props) {
  const qc = useQueryClient();
  const [selectedPatientIds, setSelectedPatientIds] = useState<number[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [draftGroupByPp, setDraftGroupByPp] = useState<Record<number, number>>({});

  const { data: patients } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => {
      const r = await apiClient.get<PatientOption[]>("/patients/");
      return r.data;
    },
  });

  const { data: groups } = useQuery({
    queryKey: ["study-groups", projectId],
    queryFn: async () => {
      const r = await apiClient.get<StudyGroupRow[]>("/studies/groups/", {
        params: { project: projectId },
      });
      return r.data;
    },
  });

  const { data: pendingBatches } = useQuery({
    queryKey: ["grouping-batches", projectId],
    queryFn: async () => {
      const r = await apiClient.get<GroupingBatchRow[]>("/studies/grouping-batches/", {
        params: { project: projectId },
      });
      return r.data.filter((b) => b.status === "pending");
    },
  });

  useEffect(() => {
    if (!activeBatchId && pendingBatches?.length) {
      setActiveBatchId(pendingBatches[0].id);
    }
  }, [pendingBatches, activeBatchId]);

  const { data: batchMembers } = useQuery({
    queryKey: ["project-patients", projectId, "batch", activeBatchId],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>("/studies/project-patients/", {
        params: { project: projectId, grouping_batch: activeBatchId },
      });
      return r.data;
    },
    enabled: !!activeBatchId,
  });

  useEffect(() => {
    if (!batchMembers?.length) return;
    const next: Record<number, number> = {};
    for (const row of batchMembers) {
      if (row.group != null) next[row.id] = row.group;
    }
    setDraftGroupByPp(next);
  }, [batchMembers]);

  const patientOptions = useMemo(
    () =>
      (patients ?? []).map((p) => ({
        value: p.id,
        label: `${p.name}（${p.phone}）`,
      })),
    [patients],
  );

  const groupOptions = useMemo(
    () =>
      (groups ?? []).map((g) => ({
        value: g.id,
        label: `${g.name}（比例 ${g.target_ratio}）`,
      })),
    [groups],
  );

  const createBatchMutation = useMutation({
    mutationFn: async () => {
      const resp = await apiClient.post<{
        batch_id: number;
        assignments: { project_patient_id: number; group_id: number }[];
      }>(`/studies/projects/${projectId}/create_grouping_batch/`, {
        patient_ids: selectedPatientIds,
      });
      return resp.data;
    },
    onSuccess: async (data) => {
      message.success("已生成分组草案");
      setActiveBatchId(data.batch_id);
      const map: Record<number, number> = {};
      for (const a of data.assignments) {
        map[a.project_patient_id] = a.group_id;
      }
      setDraftGroupByPp(map);
      setSelectedPatientIds([]);
      await qc.invalidateQueries({ queryKey: ["grouping-batches", projectId] });
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "创建分组批次失败");
    },
  });

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!activeBatchId || !batchMembers?.length) return;
      const assignments = batchMembers.map((row) => ({
        project_patient_id: row.id,
        group_id: draftGroupByPp[row.id] ?? row.group ?? groups?.[0]?.id,
      }));
      await apiClient.post(`/studies/grouping-batches/${activeBatchId}/confirm/`, {
        assignments,
      });
    },
    onSuccess: async () => {
      message.success("分组已确认");
      setActiveBatchId(null);
      await qc.invalidateQueries({ queryKey: ["grouping-batches", projectId] });
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "确认失败");
    },
  });

  const pendingBatchOptions = useMemo(
    () =>
      (pendingBatches ?? []).map((b) => ({
        value: b.id,
        label: `批次 #${b.id}（待确认）`,
      })),
    [pendingBatches],
  );

  const batchPending =
    !!activeBatchId && pendingBatches?.some((b) => b.id === activeBatchId);

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Alert
        type="info"
        message="从全局患者列表选择患者加入项目后，系统会按项目分组比例生成随机分组草案。确认前可调整，确认后不可修改。"
      />

      <Card title="新建分组批次">
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            请选择一名或多名全局患者；提交后将创建分组批次并写入草案（需项目下已有启用分组）。
          </Typography.Text>
          <Select
            mode="multiple"
            style={{ width: "100%" }}
            placeholder="选择患者（可多选）"
            options={patientOptions}
            value={selectedPatientIds}
            onChange={setSelectedPatientIds}
            optionFilterProp="label"
            showSearch
          />
          <Button
            type="primary"
            disabled={!selectedPatientIds.length || !groups?.length}
            loading={createBatchMutation.isPending}
            onClick={() => createBatchMutation.mutate()}
          >
            生成随机分组草案
          </Button>
        </Space>
      </Card>

      <Card
        title="待确认分组草案"
        extra={
          <Space wrap>
            {pendingBatchOptions.length > 0 && (
              <Select
                style={{ minWidth: 220 }}
                placeholder="切换待确认批次"
                options={pendingBatchOptions}
                value={activeBatchId}
                onChange={(v) => setActiveBatchId(v)}
                allowClear
              />
            )}
            <Button
              type="primary"
              disabled={!activeBatchId || !batchPending || !batchMembers?.length}
              loading={confirmMutation.isPending}
              onClick={() => confirmMutation.mutate()}
            >
              确认分组
            </Button>
          </Space>
        }
      >
        <Table<ProjectPatientRow>
          rowKey="id"
          loading={!batchMembers && !!activeBatchId}
          dataSource={batchMembers ?? []}
          columns={[
            { title: "患者", dataIndex: "patient_name" },
            {
              title: "草案分组",
              key: "group",
              render: (_, row) => (
                <Select
                  style={{ minWidth: 200 }}
                  options={groupOptions}
                  value={draftGroupByPp[row.id] ?? row.group ?? undefined}
                  disabled={!batchPending}
                  onChange={(gid) =>
                    setDraftGroupByPp((prev) => ({ ...prev, [row.id]: gid }))
                  }
                />
              ),
            },
            {
              title: "分组状态",
              dataIndex: "grouping_status",
              render: (v: string) => (v === "pending" ? "待确认" : v === "confirmed" ? "已确认" : v),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
