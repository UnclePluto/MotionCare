import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { isAxiosError } from "axios";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
import { EnrollProjectsModal } from "./components/EnrollProjectsModal";
import { ageFromBirthDate } from "./ageFromBirthDate";
import { buildPatientDeleteModalCopy } from "./patientDeleteModalCopy";

type Patient = {
  id: number;
  name: string;
  phone: string;
  gender?: string | null;
  birth_date?: string | null;
  age?: number | null;
  primary_doctor_name?: string | null;
  symptom_note?: string | null;
  is_active?: boolean;
};

type StudyProject = { id: number; name: string };

type ProjectPatientRow = {
  id: number;
  project: number;
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string;
};

const genderLabel: Record<string, string> = {
  male: "男",
  female: "女",
  unknown: "未知",
};

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  if ("detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "detail" in (d as object)) {
      const inner = (d as { detail?: unknown }).detail;
      if (typeof inner === "string") return inner;
    }
  }
  return null;
}

export function PatientDetailPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { patientId } = useParams();
  const id = Number(patientId);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);

  const { data: patient, isLoading, isError, error } = useQuery({
    queryKey: ["patient", patientId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<Patient>(`/patients/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const { data: projectPatients = [], isLoading: ppLoading } = useQuery({
    queryKey: ["project-patients", "patient", id],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>(`/studies/project-patients/?patient=${id}`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const projectNameById = useMemo(
    () => Object.fromEntries(projects.map((p) => [p.id, p.name])) as Record<number, string>,
    [projects],
  );

  const deleteCopy = useMemo(
    () => buildPatientDeleteModalCopy(projectPatients, projectNameById),
    [projectPatients, projectNameById],
  );

  const deleteMutation = useMutation({
    mutationFn: async () => {
      await apiClient.delete(`/patients/${id}/`);
    },
    onSuccess: async () => {
      message.success("患者档案已删除");
      setDeleteModalOpen(false);
      setDeleteBlockedReason(null);
      await qc.invalidateQueries({ queryKey: ["patients"] });
      navigate("/patients");
    },
    onError: (err) => {
      const d = backendDetail(err);
      setDeleteBlockedReason(d ?? "删除失败，请稍后重试或联系管理员。");
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: async () => {
      await apiClient.patch(`/patients/${id}/`, { is_active: false });
    },
    onSuccess: async () => {
      message.success("档案已停用");
      setDeactivateModalOpen(false);
      await qc.invalidateQueries({ queryKey: ["patient", String(id)] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err) => message.error(backendDetail(err) ?? "停用失败"),
  });

  const enableMutation = useMutation({
    mutationFn: async () => {
      await apiClient.patch(`/patients/${id}/`, { is_active: true });
    },
    onSuccess: async () => {
      message.success("档案已重新启用");
      await qc.invalidateQueries({ queryKey: ["patient", String(id)] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err) => message.error(backendDetail(err) ?? "启用失败"),
  });

  const openDeleteModal = () => {
    setDeleteBlockedReason(null);
    setDeleteModalOpen(true);
  };

  const patientActive = patient?.is_active !== false;

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的患者 ID" />;
  }

  if (isError) {
    const d = backendDetail(error);
    return <Alert type="error" message={d ?? "患者不存在或无权限访问"} />;
  }

  const displayAge =
    patient?.birth_date != null && patient.birth_date !== ""
      ? String(ageFromBirthDate(dayjs(patient.birth_date)))
      : "—";

  return (
    <Card
      loading={isLoading}
      title={patient ? patient.name : "患者详情"}
      extra={
        <Space wrap>
          <Button type="primary" onClick={() => navigate(`/patients/${id}/edit`)}>
            编辑档案
          </Button>
          <Button onClick={() => setEnrollOpen(true)}>加入研究项目</Button>
          {patientActive ? (
            <Button onClick={() => setDeactivateModalOpen(true)}>停用档案</Button>
          ) : (
            <Button type="primary" onClick={() => void enableMutation.mutate()} loading={enableMutation.isPending}>
              重新启用档案
            </Button>
          )}
          <Button danger onClick={openDeleteModal}>
            删除档案
          </Button>
        </Space>
      }
    >
      {patient && (
        <>
          <Descriptions bordered column={1} size="small" style={{ maxWidth: 640 }}>
            <Descriptions.Item label="姓名">{patient.name}</Descriptions.Item>
            <Descriptions.Item label="性别">
              {patient.gender ? genderLabel[patient.gender] ?? patient.gender : "—"}
            </Descriptions.Item>
            <Descriptions.Item label="出生日期">
              {patient.birth_date ? patient.birth_date : "—"}
            </Descriptions.Item>
            <Descriptions.Item label="年龄">{displayAge}</Descriptions.Item>
            <Descriptions.Item label="手机号">{patient.phone}</Descriptions.Item>
            <Descriptions.Item label="主治医生">
              {patient.primary_doctor_name ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="备注">
              {patient.symptom_note?.trim() ? patient.symptom_note : "—"}
            </Descriptions.Item>
            <Descriptions.Item label="档案状态">
              <Space>
                <Tag color={patientActive ? "green" : "default"}>{patientActive ? "启用" : "已停用"}</Tag>
                <Typography.Text type="secondary">
                  停用或重新启用请使用右上角按钮；人口学信息请在「编辑档案」中修改。
                </Typography.Text>
              </Space>
            </Descriptions.Item>
          </Descriptions>

          <Divider orientation="left">研究项目参与</Divider>
          <Table<ProjectPatientRow>
            rowKey="id"
            loading={ppLoading}
            dataSource={projectPatients}
            pagination={false}
            columns={[
              {
                title: "项目名称",
                key: "projectName",
                render: (_: unknown, row) => projectNameById[row.project] ?? `项目 #${row.project}`,
              },
              {
                title: "分组",
                dataIndex: "group_name",
                render: (v: string | null) => v ?? "—",
              },
              {
                title: "操作",
                key: "crf",
                render: (_: unknown, row) => (
                  <Link to={`/crf?projectPatientId=${row.id}`}>打开 CRF</Link>
                ),
              },
            ]}
          />

          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="随访与访视"
            description="后续版本将在此关联访视计划与 CRF 随访入口；本期请从上方「打开 CRF」进入录入。"
          />

          <EnrollProjectsModal open={enrollOpen} onClose={() => setEnrollOpen(false)} patientId={id} />

          <DestructiveActionModal
            open={deleteModalOpen}
            title="确认删除患者档案？"
            okText="删除"
            impactSummary={deleteCopy.summary}
            blockedReason={deleteCopy.blocked ?? deleteBlockedReason}
            confirmLoading={deleteMutation.isPending}
            onCancel={() => {
              setDeleteModalOpen(false);
              setDeleteBlockedReason(null);
            }}
            onConfirm={() => {
              if (deleteCopy.blocked) return;
              void deleteMutation.mutateAsync();
            }}
          />

          <DestructiveActionModal
            open={deactivateModalOpen}
            title="确认停用患者档案？"
            okText="停用"
            impactSummary={[
              "患者列表等默认视图将隐藏该档案（仍可通过管理端筛选或搜索策略查看，以实际列表逻辑为准）。",
              "停用期间不可再通过本系统为该患者执行「加入研究项目」等依赖启用档案的操作。",
              "已存在的研究项目入组、处方与训练记录不会被本操作自动删除；若需退出项目请在各项目看板解绑。",
            ]}
            confirmLoading={deactivateMutation.isPending}
            onCancel={() => setDeactivateModalOpen(false)}
            onConfirm={() => void deactivateMutation.mutateAsync()}
          />
        </>
      )}
    </Card>
  );
}
