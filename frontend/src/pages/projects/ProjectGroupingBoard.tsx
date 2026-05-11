import { HolderOutlined } from "@ant-design/icons";
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCorners,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Checkbox,
  InputNumber,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { ratiosToTargetRatios, targetRatiosToDisplayPercents } from "./groupingBoardUtils";

type PatientOption = { id: number; name: string; phone: string; gender: string };
type StudyGroupRow = {
  id: number;
  name: string;
  target_ratio: number;
  sort_order: number;
  is_active: boolean;
};
type ProjectPatientRow = {
  id: number;
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  grouping_status: string;
};
type GroupingBatchRow = { id: number; project: number; status: string };

type Props = {
  projectId: number;
};

const genderLabel: Record<string, string> = {
  male: "男",
  female: "女",
  unknown: "未知",
};

function phoneTail(phone: string): string {
  const d = phone.replace(/\D/g, "");
  return d.length <= 4 ? d : d.slice(-4);
}

function DroppableGroupBody({ groupId, children }: { groupId: number; children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: `col-${groupId}` });
  return (
    <div
      ref={setNodeRef}
      style={{
        minHeight: 80,
        borderRadius: 6,
        padding: 4,
        background: isOver ? "rgba(22, 119, 255, 0.06)" : undefined,
      }}
    >
      {children}
    </div>
  );
}

function DraggablePpCard({
  row,
  patientById,
  batchPending,
}: {
  row: ProjectPatientRow;
  patientById: Record<number, PatientOption>;
  batchPending: boolean;
}) {
  const confirmed = row.grouping_status === "confirmed";
  const disabled = !batchPending || confirmed;
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `pp-${row.id}`,
    disabled,
  });
  const style: CSSProperties = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.75 : 1,
    marginBottom: 8,
  };
  const p = patientById[row.patient];
  return (
    <div ref={setNodeRef} style={style}>
      <Card size="small">
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Space align="start" style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Text strong>{row.patient_name}</Typography.Text>
            <Button
              type="text"
              size="small"
              icon={<HolderOutlined />}
              disabled={disabled}
              {...listeners}
              {...attributes}
              aria-label="拖拽调整分组"
            />
          </Space>
          <Typography.Text type="secondary">
            {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(row.patient_phone)}
          </Typography.Text>
          <Typography.Text type="secondary">
            状态：{row.grouping_status === "pending" ? "待确认" : row.grouping_status === "confirmed" ? "已确认" : row.grouping_status}
          </Typography.Text>
          <Link to={`/patients/${row.patient}`}>患者详情</Link>
        </Space>
      </Card>
    </div>
  );
}

export function ProjectGroupingBoard({ projectId }: Props) {
  const qc = useQueryClient();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const [poolSelected, setPoolSelected] = useState<number[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [draftGroupByPp, setDraftGroupByPp] = useState<Record<number, number>>({});
  const [percentByGroupId, setPercentByGroupId] = useState<Record<number, number>>({});

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

  const { data: projectPatients } = useQuery({
    queryKey: ["project-patients", projectId],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>("/studies/project-patients/", {
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

  const patientById = useMemo(
    () => Object.fromEntries((patients ?? []).map((p) => [p.id, p])) as Record<number, PatientOption>,
    [patients],
  );

  const enrolledPatientIds = useMemo(
    () => new Set((projectPatients ?? []).map((pp) => pp.patient)),
    [projectPatients],
  );

  const poolPatients = useMemo(
    () => (patients ?? []).filter((p) => !enrolledPatientIds.has(p.id)),
    [patients, enrolledPatientIds],
  );

  const activeGroups = useMemo(
    () => [...(groups ?? []).filter((g) => g.is_active)].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [groups],
  );

  useEffect(() => {
    if (!activeGroups.length) return;
    const ratios = activeGroups.map((g) => g.target_ratio);
    const percents = targetRatiosToDisplayPercents(ratios);
    const next: Record<number, number> = {};
    activeGroups.forEach((g, i) => {
      next[g.id] = percents[i] ?? 1;
    });
    setPercentByGroupId((prev) => {
      const keys = new Set(activeGroups.map((g) => g.id));
      const merged = { ...prev };
      for (const id of Object.keys(merged)) {
        if (!keys.has(Number(id))) delete merged[Number(id)];
      }
      for (const g of activeGroups) {
        if (merged[g.id] === undefined) merged[g.id] = next[g.id] ?? 1;
      }
      return merged;
    });
  }, [activeGroups]);

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

  const createBatchMutation = useMutation({
    mutationFn: async () => {
      const resp = await apiClient.post<{
        batch_id: number;
        assignments: { project_patient_id: number; group_id: number }[];
      }>(`/studies/projects/${projectId}/create_grouping_batch/`, {
        patient_ids: poolSelected,
        seed: Date.now(),
      });
      return resp.data;
    },
    onSuccess: async (data) => {
      message.success("已生成随机分组草案");
      setActiveBatchId(data.batch_id);
      const map: Record<number, number> = {};
      for (const a of data.assignments) {
        map[a.project_patient_id] = a.group_id;
      }
      setDraftGroupByPp(map);
      setPoolSelected([]);
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
      const missing: number[] = [];
      const assignments: { project_patient_id: number; group_id: number }[] = [];
      for (const row of batchMembers) {
        const groupId = draftGroupByPp[row.id] ?? row.group ?? null;
        if (groupId == null) missing.push(row.id);
        else assignments.push({ project_patient_id: row.id, group_id: groupId });
      }
      if (missing.length) {
        message.error("部分患者缺少分组，请刷新页面或重新生成分组草案后再确认。");
        throw new Error("missing group for confirm");
      }
      await apiClient.post(`/studies/grouping-batches/${activeBatchId}/confirm/`, {
        assignments,
      });
    },
    onSuccess: async () => {
      message.success("分组已确认");
      setActiveBatchId(null);
      await qc.invalidateQueries({ queryKey: ["grouping-batches", projectId] });
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "确认失败");
    },
  });

  const patchGroupRatioMutation = useMutation({
    mutationFn: async (payload: { groupId: number; ratio: number }[]) => {
      for (const { groupId, ratio } of payload) {
        await apiClient.patch(`/studies/groups/${groupId}/`, { target_ratio: ratio });
      }
    },
    onSuccess: async () => {
      message.success("占比已更新");
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
    },
    onError: () => message.error("更新占比失败"),
  });

  const deleteGroupMutation = useMutation({
    mutationFn: async (groupId: number) => {
      await apiClient.delete(`/studies/groups/${groupId}/`);
    },
    onSuccess: async () => {
      message.success("分组已删除");
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "删除分组失败");
    },
  });

  const patchPpGroupMutation = useMutation({
    mutationFn: async ({ ppId, groupId }: { ppId: number; groupId: number }) => {
      await apiClient.patch(`/studies/project-patients/${ppId}/`, { group: groupId });
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "更新分组失败");
    },
  });

  const applyPercents = () => {
    const ordered = activeGroups;
    const pcts = ordered.map((g) => percentByGroupId[g.id] ?? 0);
    const sum = pcts.reduce((a, b) => a + b, 0);
    if (sum !== 100) {
      message.warning("各列占比合计须为 100。");
      return;
    }
    if (pcts.some((p) => p <= 0)) {
      message.error("每列占比须为大于 0 的整数（合计 100）；请勿使用 0%。");
      return;
    }
    const weights = ratiosToTargetRatios(pcts);
    patchGroupRatioMutation.mutate(ordered.map((g, i) => ({ groupId: g.id, ratio: weights[i] })));
  };

  const confirmDeleteGroup = (g: StudyGroupRow) => {
    Modal.confirm({
      title: `删除分组「${g.name}」？`,
      content: "若分组下仍有患者关联，后端可能拒绝删除。",
      okText: "删除",
      okType: "danger",
      onOk: () => deleteGroupMutation.mutateAsync(g.id),
    });
  };

  const onDraftGroupChange = (ppId: number, groupId: number) => {
    setDraftGroupByPp((prev) => ({ ...prev, [ppId]: groupId }));
    patchPpGroupMutation.mutate({ ppId, groupId });
  };

  const handleDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || !batchPending) return;
    const aid = String(active.id);
    if (!aid.startsWith("pp-")) return;
    const ppId = Number(aid.slice(3));
    const row = batchMembers?.find((r) => r.id === ppId);
    if (!row || row.grouping_status === "confirmed") return;

    let targetGroupId: number | null = null;
    const oid = String(over.id);
    if (oid.startsWith("col-")) {
      targetGroupId = Number(oid.slice(4));
    } else if (oid.startsWith("pp-")) {
      const otherId = Number(oid.slice(3));
      const other = batchMembers?.find((r) => r.id === otherId);
      if (other) {
        targetGroupId = draftGroupByPp[other.id] ?? other.group ?? null;
      }
    }
    if (targetGroupId == null) return;
    const current = draftGroupByPp[row.id] ?? row.group ?? undefined;
    if (current === targetGroupId) return;
    onDraftGroupChange(ppId, targetGroupId);
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card size="small">
        <Space wrap align="center">
          <Button size="small" onClick={applyPercents} loading={patchGroupRatioMutation.isPending}>
            应用占比到权重
          </Button>
          <Typography.Text type="secondary">待确认批次</Typography.Text>
          {pendingBatchOptions.length > 0 ? (
            <Select
              style={{ minWidth: 220 }}
              options={pendingBatchOptions}
              value={activeBatchId}
              onChange={(v) => setActiveBatchId(v)}
              allowClear
              placeholder="选择批次"
            />
          ) : (
            <Typography.Text>暂无</Typography.Text>
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
      </Card>

      <Card title="患者池（尚未加入本项目）" size="small">
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          勾选患者后点击「随机分组」生成待确认草案；列内卡片可拖拽到其它列以调整草案分组（已确认的记录不可拖拽）。
        </Typography.Paragraph>
        <Checkbox.Group
          style={{ display: "flex", flexWrap: "wrap", gap: 8 }}
          value={poolSelected}
          onChange={(v) => setPoolSelected(v as number[])}
        >
          {poolPatients.map((p) => (
            <Checkbox key={p.id} value={p.id}>
              <Tag>
                {p.name} · {genderLabel[p.gender] ?? p.gender} · 尾号 {phoneTail(p.phone)}
              </Tag>
            </Checkbox>
          ))}
        </Checkbox.Group>
        <Button
          type="primary"
          style={{ marginTop: 12 }}
          disabled={!poolSelected.length || !activeGroups.length}
          loading={createBatchMutation.isPending}
          onClick={() => createBatchMutation.mutate()}
        >
          随机分组
        </Button>
      </Card>

      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={handleDragEnd}>
        <div style={{ display: "flex", gap: 12, overflowX: "auto", alignItems: "flex-start" }}>
          {activeGroups.map((g) => (
            <Card
              key={g.id}
              size="small"
              style={{ minWidth: 240, flex: "0 0 auto" }}
              title={
                <Space direction="vertical" size={4} style={{ width: "100%" }}>
                  <Space style={{ width: "100%", justifyContent: "space-between" }}>
                    <Typography.Text strong>{g.name}</Typography.Text>
                    <Button
                      type="text"
                      danger
                      size="small"
                      onClick={() => confirmDeleteGroup(g)}
                      loading={deleteGroupMutation.isPending}
                    >
                      −
                    </Button>
                  </Space>
                  <Space>
                    <Typography.Text type="secondary">占比 %</Typography.Text>
                    <InputNumber
                      min={0}
                      max={100}
                      size="small"
                      value={percentByGroupId[g.id]}
                      onChange={(v) =>
                        setPercentByGroupId((prev) => ({
                          ...prev,
                          [g.id]: typeof v === "number" ? v : 0,
                        }))
                      }
                    />
                  </Space>
                </Space>
              }
            >
              <DroppableGroupBody groupId={g.id}>
                {(batchMembers ?? [])
                  .filter((row) => (draftGroupByPp[row.id] ?? row.group) === g.id)
                  .map((row) => (
                    <DraggablePpCard
                      key={row.id}
                      row={row}
                      patientById={patientById}
                      batchPending={!!batchPending}
                    />
                  ))}
              </DroppableGroupBody>
            </Card>
          ))}
        </div>
      </DndContext>
    </Space>
  );
}
