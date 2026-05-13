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
import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
import {
  assignPatientsToGroups,
  balancePercents,
  getPercentValidationError,
  groupsWithDraftPercents,
} from "./groupingBoardUtils";

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

const PATIENT_DRAG_MIME = "application/x-motioncare-patient-id";

type Props = {
  projectId: number;
  groupRevision?: number;
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
      <Card size="small" style={{ opacity: 0.6 }} styles={{ body: { padding: 10 } }}>
        <div className="patient-card-line" data-testid={`confirmed-patient-${row.patient}`}>
          <Typography.Text className="patient-name" strong>
            {row.patient_name}
          </Typography.Text>
          <Tag>已确认</Tag>
          <Typography.Text className="patient-meta" type="secondary">
            {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(row.patient_phone)}
          </Typography.Text>
          <span className="patient-card-actions">
            <Link to={`/patients/${row.patient}`}>详情</Link>
            <Button type="link" danger size="small" style={{ padding: 0 }} onClick={() => onRequestUnbind(row)}>
              解绑
            </Button>
          </span>
        </div>
      </Card>
    </div>
  );
}

function LocalAssignmentCard({
  assignment,
  patientById,
  onRemove,
  onDragStart,
}: {
  assignment: LocalAssignmentRow;
  patientById: Record<number, PatientOption>;
  onRemove: (patientId: number) => void;
  onDragStart: (patientId: number, event: DragEvent<HTMLDivElement>) => void;
}) {
  const p = patientById[assignment.patientId];
  return (
    <div
      data-testid={`local-assignment-${assignment.patientId}`}
      draggable
      onDragStart={(event) => onDragStart(assignment.patientId, event)}
      style={{ marginBottom: 8, cursor: "grab" }}
    >
      <Card size="small" styles={{ body: { padding: 10 } }}>
        <div className="patient-card-line">
          <Typography.Text className="patient-name" strong>
            {p?.name ?? `患者 ${assignment.patientId}`}
          </Typography.Text>
          <Tag color="blue">本轮</Tag>
          <Typography.Text className="patient-meta" type="secondary">
            {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(p?.phone ?? "")}
          </Typography.Text>
          <span className="patient-card-actions">
            <Link to={`/patients/${assignment.patientId}`}>详情</Link>
            <Button
              type="link"
              danger
              size="small"
              style={{ padding: 0 }}
              onClick={() => onRemove(assignment.patientId)}
            >
              移除
            </Button>
          </span>
        </div>
      </Card>
    </div>
  );
}

export function ProjectGroupingBoard({ projectId, groupRevision = 0 }: Props) {
  const qc = useQueryClient();
  const appliedGroupRevisionRef = useRef(0);
  const [poolSelected, setPoolSelected] = useState<number[]>([]);
  const [localAssignments, setLocalAssignments] = useState<LocalAssignmentRow[]>([]);
  const [percentByGroupId, setPercentByGroupId] = useState<Record<number, number>>({});
  const [isPercentDirty, setIsPercentDirty] = useState(false);
  const [deleteGroupTarget, setDeleteGroupTarget] = useState<StudyGroupRow | null>(null);
  const [unbindTarget, setUnbindTarget] = useState<ProjectPatientRow | null>(null);

  useEffect(() => {
    setLocalAssignments([]);
    setPoolSelected([]);
    setPercentByGroupId({});
    setIsPercentDirty(false);
    appliedGroupRevisionRef.current = 0;
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

  const activeGroupIds = useMemo(() => new Set(activeGroups.map((g) => g.id)), [activeGroups]);

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
    if (isPercentDirty) return;
    setPercentByGroupId(Object.fromEntries(activeGroups.map((g) => [g.id, g.target_ratio])));
  }, [activeGroups, isPercentDirty]);

  useEffect(() => {
    if (!groupRevision || groupRevision === appliedGroupRevisionRef.current || !activeGroups.length) return;
    setPercentByGroupId(balancePercents(activeGroups.map((g) => g.id)));
    setIsPercentDirty(true);
    appliedGroupRevisionRef.current = groupRevision;
  }, [activeGroups, groupRevision]);

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
      const groupRatios = activeGroups.map((g) => ({
        group_id: g.id,
        target_ratio: percentByGroupId[g.id] ?? g.target_ratio,
      }));
      await apiClient.post(`/studies/projects/${projectId}/confirm-grouping/`, {
        group_ratios: groupRatios,
        assignments: localAssignments.map((a) => ({ patient_id: a.patientId, group_id: a.groupId })),
      });
    },
    onSuccess: async () => {
      const hadAssignments = localAssignments.length > 0;
      message.success(hadAssignments ? "分组已确认" : "占比已保存");
      setLocalAssignments([]);
      setPoolSelected([]);
      setIsPercentDirty(false);
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: (err: { response?: { status?: number; data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "确认失败");
      const status = err.response?.status;
      const shouldClearDraft = Boolean(err.response) && (status == null || status < 500);
      if (shouldClearDraft) {
        setLocalAssignments([]);
        setPoolSelected([]);
        void qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
        void qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
        void qc.invalidateQueries({ queryKey: ["patients"] });
      }
    },
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

  const openDeleteGroupModal = (g: StudyGroupRow) => {
    setDeleteGroupTarget(g);
  };

  const handleAssignmentDragStart = (patientId: number, event: DragEvent<HTMLDivElement>) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(PATIENT_DRAG_MIME, String(patientId));
  };

  const handleGroupDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const handleGroupDrop = (groupId: number, event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!activeGroupIds.has(groupId)) return;

    const rawPatientId = event.dataTransfer.getData(PATIENT_DRAG_MIME);
    if (!rawPatientId) return;

    const patientId = Number(rawPatientId);
    if (!Number.isInteger(patientId) || patientId <= 0) return;

    setLocalAssignments((prev) => {
      if (!prev.some((assignment) => assignment.patientId === patientId)) return prev;
      return prev.map((assignment) => (assignment.patientId === patientId ? { ...assignment, groupId } : assignment));
    });
  };

  const countPatientsInGroup = (groupId: number) =>
    (projectPatients ?? []).filter((row) => row.group === groupId).length +
    localAssignments.filter((a) => a.groupId === groupId).length;

  const hasEligibleSelection = poolSelected.some((id) => !confirmedPatientIds.has(id));
  const activePercents = activeGroups.map((g) => percentByGroupId[g.id] ?? g.target_ratio);
  const percentValidationError = getPercentValidationError(activePercents);

  const runLocalRandomize = () => {
    const eligibleIds = poolSelected.filter((id) => !confirmedPatientIds.has(id));
    if (!eligibleIds.length) {
      message.warning("请先选择至少一名未确认入组患者。");
      return;
    }
    const validationError = getPercentValidationError(activePercents);
    if (validationError) {
      message.warning(validationError);
      return;
    }
    try {
      setLocalAssignments(
        assignPatientsToGroups(eligibleIds, groupsWithDraftPercents(activeGroups, percentByGroupId), Date.now()),
      );
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

  const confirmCurrentDraft = () => {
    if (percentValidationError) {
      message.warning(percentValidationError);
      return;
    }
    confirmGroupingMutation.mutate();
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card size="small">
        <Space wrap align="center">
          <Button type="primary" disabled={!hasEligibleSelection || !activeGroups.length} onClick={runLocalRandomize}>
            随机分组
          </Button>
          <Button
            type="primary"
            style={{ backgroundColor: "#16a34a", borderColor: "#16a34a" }}
            disabled={!activeGroups.length}
            loading={confirmGroupingMutation.isPending}
            onClick={confirmCurrentDraft}
          >
            确认分组
          </Button>
          <Typography.Text type={percentValidationError ? "danger" : "secondary"}>
            {percentValidationError ?? "占比与本轮随机结果仅在确认后保存。"}
          </Typography.Text>
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
      </Card>

      <div style={{ display: "flex", gap: 12, overflowX: "auto", alignItems: "flex-start" }}>
        {visibleGroups.map((g) => (
          <Card
            key={g.id}
            data-testid={`group-card-${g.id}`}
            className="group-card"
            size="small"
            style={{ minWidth: 460, flex: "0 0 460px", position: "relative" }}
            title={
              <Space direction="vertical" size={4} style={{ width: "100%", paddingRight: 32 }}>
                <Space style={{ width: "100%", justifyContent: "space-between" }}>
                  <Space>
                    <Typography.Text strong>{g.name}</Typography.Text>
                    {!g.is_active ? <Tag>已停用</Tag> : null}
                  </Space>
                </Space>
                <Space>
                  <Typography.Text type="secondary">占比</Typography.Text>
                  <Space.Compact size="small" className="ratio-input-compact">
                    <InputNumber
                      min={1}
                      max={100}
                      controls={false}
                      size="small"
                      aria-label={`${g.name}占比`}
                      style={{ width: 54 }}
                      value={percentByGroupId[g.id]}
                      disabled={!g.is_active}
                      onChange={(v) => {
                        setIsPercentDirty(true);
                        setPercentByGroupId((prev) => ({
                          ...prev,
                          [g.id]: typeof v === "number" ? Math.round(v) : 0,
                        }));
                      }}
                    />
                    <span className={g.is_active ? "ratio-input-addon" : "ratio-input-addon ratio-input-addon-disabled"}>
                      %
                    </span>
                  </Space.Compact>
                </Space>
              </Space>
            }
          >
            <Button
              type="text"
              danger
              size="small"
              aria-label={`删除${g.name}`}
              className="group-delete-bubble"
              onClick={() => openDeleteGroupModal(g)}
              loading={deleteGroupMutation.isPending}
              disabled={!g.is_active}
              style={{
                position: "absolute",
                right: 8,
                top: 8,
                width: 24,
                height: 24,
                minWidth: 24,
                borderRadius: 9999,
                zIndex: 2,
              }}
            >
              ×
            </Button>
            <div
              data-testid={`group-drop-${g.id}`}
              onDragOver={g.is_active ? handleGroupDragOver : undefined}
              onDrop={g.is_active ? (event) => handleGroupDrop(g.id, event) : undefined}
              style={{ minHeight: 80, borderRadius: 6, padding: 4 }}
            >
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
                    onDragStart={handleAssignmentDragStart}
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
