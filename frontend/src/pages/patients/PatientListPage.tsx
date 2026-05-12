import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  message,
} from "antd";
import { isAxiosError } from "axios";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
import { maskPhoneForList } from "./phoneMask";
import { buildPatientDeleteModalCopy } from "./patientDeleteModalCopy";

type PatientRow = {
  id: number;
  name: string;
  gender: string;
  age: number | null;
  phone: string;
  primary_doctor: number | null;
  primary_doctor_name?: string | null;
};

type ProjectPatientRow = {
  id: number;
  project: number;
  patient_name: string;
  group_name: string | null;
  grouping_status: string;
};

type StudyProject = { id: number; name: string };

const genderLabel: Record<string, string> = {
  male: "男",
  female: "女",
  unknown: "未知",
};

type CreatePatientValues = {
  name: string;
  gender: "male" | "female" | "unknown";
  age?: number | null;
  phone: string;
  symptom_note?: string;
};

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  const rec = data as Record<string, unknown>;
  const detail = rec.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "msg" in (item as object)) {
        return String((item as { msg: unknown }).msg);
      }
      try {
        return JSON.stringify(item);
      } catch {
        return String(item);
      }
    });
    const joined = parts.filter(Boolean).join("；");
    if (joined) return joined;
  }
  const fieldParts = Object.entries(rec)
    .filter(([k]) => k !== "detail")
    .map(([k, v]) => {
      if (Array.isArray(v)) return `${k}: ${v.map(String).join(", ")}`;
      if (typeof v === "string") return `${k}: ${v}`;
      return `${k}: ${JSON.stringify(v)}`;
    });
  if (fieldParts.length) return fieldParts.join("；");
  return null;
}

export function PatientListPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<CreatePatientValues>();
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);
  const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => {
      const r = await apiClient.get<PatientRow[]>("/patients/");
      return r.data;
    },
  });

  const { data: deleteProjectPatients = [] } = useQuery({
    queryKey: ["project-patients", "for-delete", deleteTargetId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>(
        `/studies/project-patients/?patient=${deleteTargetId}`,
      );
      return r.data;
    },
    enabled: deleteTargetId != null,
  });

  const { data: deleteProjects = [] } = useQuery({
    queryKey: ["study-projects", "for-delete", deleteTargetId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
    enabled: deleteTargetId != null,
  });

  const deleteProjectNameById = useMemo(
    () => Object.fromEntries(deleteProjects.map((p) => [p.id, p.name])) as Record<number, string>,
    [deleteProjects],
  );

  const deleteCopy = useMemo(
    () => buildPatientDeleteModalCopy(deleteProjectPatients, deleteProjectNameById),
    [deleteProjectPatients, deleteProjectNameById],
  );

  const createMutation = useMutation({
    mutationFn: async (values: CreatePatientValues) => {
      await apiClient.post("/patients/", {
        name: values.name.trim(),
        gender: values.gender,
        age: values.age ?? null,
        phone: values.phone.trim(),
        primary_doctor: me?.id ?? null,
        symptom_note: (values.symptom_note ?? "").trim(),
        is_active: true,
      });
    },
    onSuccess: async () => {
      message.success("患者已创建");
      setOpen(false);
      form.resetFields();
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err: unknown) => {
      message.error(backendDetail(err) ?? "创建失败（手机号可能已存在）");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (deleteTargetId == null) return;
      await apiClient.delete(`/patients/${deleteTargetId}/`);
    },
    onSuccess: async () => {
      message.success("患者档案已删除");
      setDeleteTargetId(null);
      setDeleteBlockedReason(null);
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err: unknown) => {
      const d = backendDetail(err);
      setDeleteBlockedReason(d ?? "删除失败，请稍后重试或联系管理员。");
    },
  });

  const openDeleteFor = (rowId: number) => {
    setDeleteBlockedReason(null);
    setDeleteTargetId(rowId);
  };

  return (
    <Card
      title="患者档案"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          新建患者
        </Button>
      }
    >
      <Table<PatientRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        onRow={(record) => ({
          onClick: () => navigate(`/patients/${record.id}`),
          style: { cursor: "pointer" },
        })}
        columns={[
          { title: "姓名", dataIndex: "name" },
          {
            title: "性别",
            dataIndex: "gender",
            render: (v: string) => genderLabel[v] ?? v,
          },
          { title: "年龄", dataIndex: "age" },
          {
            title: "手机号",
            dataIndex: "phone",
            render: (v: string) => maskPhoneForList(v ?? ""),
          },
          {
            title: "主治医生",
            dataIndex: "primary_doctor_name",
            render: (_: unknown, row) => row.primary_doctor_name ?? "—",
          },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
                <Button
                  type="link"
                  style={{ padding: 0 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/patients/${row.id}/edit`);
                  }}
                >
                  编辑
                </Button>
                <Button
                  type="link"
                  danger
                  style={{ padding: 0 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    openDeleteFor(row.id);
                  }}
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <DestructiveActionModal
        open={deleteTargetId != null}
        title="确认删除患者档案？"
        okText="删除"
        impactSummary={deleteCopy.summary}
        blockedReason={deleteCopy.blocked ?? deleteBlockedReason}
        confirmLoading={deleteMutation.isPending}
        onCancel={() => {
          setDeleteTargetId(null);
          setDeleteBlockedReason(null);
        }}
        onConfirm={() => {
          if (deleteCopy.blocked) return;
          void deleteMutation.mutateAsync();
        }}
      />

      <Modal
        title="新建患者"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form<CreatePatientValues>
          form={form}
          layout="vertical"
          initialValues={{ gender: "unknown" }}
          onFinish={(v) => createMutation.mutate(v)}
        >
          <Form.Item
            label="姓名"
            name="name"
            rules={[{ required: true, message: "请输入姓名" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="性别" name="gender" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "male", label: "男" },
                { value: "female", label: "女" },
                { value: "unknown", label: "未知" },
              ]}
            />
          </Form.Item>
          <Form.Item label="年龄" name="age">
            <InputNumber min={0} max={130} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            label="手机号"
            name="phone"
            rules={[{ required: true, message: "请输入手机号" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="备注" name="symptom_note">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
                保存
              </Button>
              <Button onClick={() => setOpen(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
