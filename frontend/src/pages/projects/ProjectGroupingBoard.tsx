import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Checkbox,
  InputNumber,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
import { assignPatientsToGroups, ratiosToTargetRatios, targetRatiosToDisplayPercents } from "./groupingBoardUtils";

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
};
type LocalAssignmentRow = { patientId: number; groupId: number };

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

function ConfirmedPatientCard({
  row,
  patientById,
  onRequestUnbind,
}: {
  row: ProjectPatientRow;
  patientById: Record<number, PatientOption>;
  onRequestUnbind: (row: ProjectPatientRow) => void;
}) {
  const p = patientById[row.patient];
  return (
    <div style={{ marginBottom: 8 }}>
      <Card size="small" style={{ opacity: 0.6 }}>
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Space align="start" style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Text strong>{row.patient_name}</Typography.Text>
            <Tag>已确认</Tag>
          </Space>
          <Typography.Text type="secondary">
            {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(row.patient_phone)}
          </Typography.Text>
          <Link to={`/patients/${row.patient}`}>患者详情</Link>
          <Button type="link" danger size="small" style={{ padding: 0 }} onClick={() => onRequestUnbind(row)}>
            从本项目移除
          </Button>
        </Space>
      </Card>
    </div>
  );
}

function LocalAssignmentCard({
  assignment,
  patientById,
  onRemove,
}: {
  assignment: LocalAssignmentRow;
  patientById: Record<number, PatientOption>;
  onRemove: (patientId: number) => void;
}) {
  const p = patientById[assignment.patientId];
  return (
    <div style={{ marginBottom: 8 }}>
      <Card size="small">
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Space align="start" style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Text strong>{p?.name ?? `患者 ${assignment.patientId}`}</Typography.Text>
            <Tag color="blue">本次随机</Tag>
          </Space>
          <Typography.Text type="secondary">
            {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(p?.phone ?? "")}
          </Typography.Text>
          <Link to={`/patients/${assignment.patientId}`}>患者详情</Link>
          <Button
            type="link"
            danger
            size="small"
            style={{ padding: 0 }}
            onClick={() => onRemove(assignment.patientId)}
          >
            从本次结果移除
          </Button>
        </Space>
      </Card>
    </div>
  );
}

export function ProjectGroupingBoard({ projectId }: Props) {
  const qc = useQueryClient();
  const [poolSelected, setPoolSelected] = useState<number[]>([]);
  const [localAssignments, setLocalAssignments] = useState<LocalAssignmentRow[]>([]);
  const [percentByGroupId, setPercentByGroupId] = useState<Record<number, number>>({});
  const [deleteGroupTarget, setDeleteGroupTarget] = useState<StudyGroupRow | null>(null);
  const [unbindTarget, setUnbindTarget] = useState<ProjectPatientRow | null>(null);

  useEffect(() => {
    setLocalAssignments([]);
    setPoolSelected([]);
  }, [projectId]);

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

  const patientById = useMemo(
    () => Object.fromEntries((patients ?? []).map((p) => [p.id, p])) as Record<number, PatientOption>,
    [patients],
  );

  const confirmedPatientIds = useMemo(
    () => new Set((projectPatients ?? []).map((pp) => pp.patient)),
    [projectPatients],
  );

  const activeGroups = useMemo(
    () => [...(groups ?? []).filter((g) => g.is_active)].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [groups],
  );

  const visibleGroups = useMemo(() => {
    const referencedGroupIds = new Set(
      (projectPatients ?? [])
        .map((row) => row.group)
        .filter((groupId): groupId is number => groupId != null),
    );
    return [...(groups ?? [])]
      .filter((g) => g.is_active || referencedGroupIds.has(g.id))
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  }, [groups, projectPatients]);

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

  const unbindMutation = useMutation({
    mutationFn: async (ppId: number) => {
      await apiClient.post(`/studies/project-patients/${ppId}/unbind/`);
    },
    onSuccess: async () => {
      message.success("已从本项目移除");
      setUnbindTarget(null);
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "解绑失败");
    },
  });

  const confirmGroupingMutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/studies/projects/${projectId}/confirm-grouping/`, {
        assignments: localAssignments.map((a) => ({ patient_id: a.patientId, group_id: a.groupId })),
      });
    },
    onSuccess: async () => {
      message.success("分组已确认");
      setLocalAssignments([]);
      setPoolSelected([]);
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "确认失败");
      setLocalAssignments([]);
      setPoolSelected([]);
      void qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      void qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
      void qc.invalidateQueries({ queryKey: ["patients"] });
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
      setDeleteGroupTarget(null);
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "删除分组失败");
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

  const openDeleteGroupModal = (g: StudyGroupRow) => {
    setDeleteGroupTarget(g);
  };

  const countPatientsInGroup = (groupId: number) =>
    (projectPatients ?? []).filter((row) => row.group === groupId).length +
    localAssignments.filter((a) => a.groupId === groupId).length;

  const runLocalRandomize = () => {
    const eligibleIds = poolSelected.filter((id) => !confirmedPatientIds.has(id));
    if (!eligibleIds.length) {
      message.warning("请先选择至少一名未确认入组患者。");
      return;
    }
    try {
      setLocalAssignments(assignPatientsToGroups(eligibleIds, activeGroups, Date.now()));
      message.success("已生成本次随机分组");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "随机分组失败");
    }
  };

  const handlePatientSelectionChange = (patientId: number, checked: boolean) => {
    setPoolSelected((prev) =>
      checked
        ? prev.includes(patientId)
          ? prev
          : [...prev, patientId]
        : prev.filter((id) => id !== patientId),
    );

    if (!checked) {
      setLocalAssignments((prev) => prev.filter((assignment) => assignment.patientId !== patientId));
    }
  };

  const hasEligibleSelection = poolSelected.some((id) => !confirmedPatientIds.has(id));

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card size="small">
        <Space wrap align="center">
          <Button size="small" onClick={applyPercents} loading={patchGroupRatioMutation.isPending}>
            应用占比到权重
          </Button>
          <Typography.Text type="secondary">
            当前随机结果仅保存在本页面；刷新或切换项目会丢弃，点击「确认分组」后才正式入组。
          </Typography.Text>
          <Button
            type="primary"
            disabled={!localAssignments.length}
            loading={confirmGroupingMutation.isPending}
            onClick={() => confirmGroupingMutation.mutate()}
          >
            确认分组
          </Button>
        </Space>
      </Card>

      <Card title={patients ? "全量患者" : "加载患者"} size="small">
        <Space wrap size={[8, 8]}>
          {(patients ?? []).map((p) => (
            <Checkbox
              key={p.id}
              checked={poolSelected.includes(p.id)}
              disabled={confirmedPatientIds.has(p.id)}
              aria-label={`选择患者 ${p.name}`}
              onChange={(e) => handlePatientSelectionChange(p.id, e.target.checked)}
            >
              <Tag>
                {p.name} · {genderLabel[p.gender] ?? p.gender} · 尾号 {phoneTail(p.phone)}
                {confirmedPatientIds.has(p.id) ? " · 已确认" : ""}
              </Tag>
            </Checkbox>
          ))}
        </Space>
        <Button
          type="primary"
          style={{ marginTop: 12 }}
          disabled={!hasEligibleSelection || !activeGroups.length}
          onClick={runLocalRandomize}
        >
          随机分组
        </Button>
      </Card>

      <div style={{ display: "flex", gap: 12, overflowX: "auto", alignItems: "flex-start" }}>
        {visibleGroups.map((g) => (
          <Card
            key={g.id}
            size="small"
            style={{ minWidth: 240, flex: "0 0 auto" }}
            title={
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Space style={{ width: "100%", justifyContent: "space-between" }}>
                  <Space>
                    <Typography.Text strong>{g.name}</Typography.Text>
                    {!g.is_active ? <Tag>已停用</Tag> : null}
                  </Space>
                  <Button
                    type="text"
                    danger
                    size="small"
                    onClick={() => openDeleteGroupModal(g)}
                    loading={deleteGroupMutation.isPending}
                    disabled={!g.is_active}
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
                    disabled={!g.is_active}
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
            <div style={{ minHeight: 80, borderRadius: 6, padding: 4 }}>
              {(projectPatients ?? [])
                .filter((row) => row.group === g.id)
                .map((row) => (
                  <ConfirmedPatientCard
                    key={row.id}
                    row={row}
                    patientById={patientById}
                    onRequestUnbind={(r) => setUnbindTarget(r)}
                  />
                ))}
              {localAssignments
                .filter((a) => a.groupId === g.id)
                .map((assignment) => (
                  <LocalAssignmentCard
                    key={assignment.patientId}
                    assignment={assignment}
                    patientById={patientById}
                    onRemove={(patientId) =>
                      setLocalAssignments((prev) => prev.filter((a) => a.patientId !== patientId))
                    }
                  />
                ))}
            </div>
          </Card>
        ))}
      </div>

      <DestructiveActionModal
        open={deleteGroupTarget != null}
        title={deleteGroupTarget ? `删除分组「${deleteGroupTarget.name}」？` : "删除分组？"}
        okText="删除"
        impactSummary={
          deleteGroupTarget
            ? [
                `将请求删除分组「${deleteGroupTarget.name}」及其列配置。`,
                `当前列内约有 ${countPatientsInGroup(deleteGroupTarget.id)} 名患者卡片；若后端仍有关联，删除将被拒绝。`,
              ]
            : []
        }
        confirmLoading={deleteGroupMutation.isPending}
        onCancel={() => setDeleteGroupTarget(null)}
        onConfirm={() => {
          if (!deleteGroupTarget) return;
          void deleteGroupMutation.mutateAsync(deleteGroupTarget.id);
        }}
      />

      <DestructiveActionModal
        open={unbindTarget != null}
        title={unbindTarget ? `将「${unbindTarget.patient_name}」从本项目移除？` : "解绑？"}
        okText="确认移除"
        impactSummary={[
          "将删除该患者在本项目下的入组关系（ProjectPatient），且不可从本入口恢复。",
          "若已存在与本项目、该入组关系相关的 CRF 访视或导出记录，将按服务端策略作废或清理；关联处方将标记为已终止。",
          "医生端默认列表将不再展示上述已终止处方。",
          "移除后该患者会重新出现在「全量患者」，需要时可勾选再次参与随机。",
        ]}
        confirmLoading={unbindMutation.isPending}
        onCancel={() => setUnbindTarget(null)}
        onConfirm={() => {
          if (!unbindTarget) return;
          void unbindMutation.mutateAsync(unbindTarget.id);
        }}
      />
    </Space>
  );
}
