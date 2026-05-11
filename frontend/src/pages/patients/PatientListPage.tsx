import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { isAxiosError } from "axios";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { DestructiveActionModal } from "../components/DestructiveActionModal";

type PatientRow = {
  id: number;
  name: string;
  gender: string;
  age: number | null;
  phone: string;
  primary_doctor: number | null;
  primary_doctor_name?: string | null;
};

type PatientDetail = PatientRow & {
  birth_date?: string | null;
  symptom_note?: string | null;
  is_active?: boolean;
};

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

type EditPatientValues = {
  name: string;
  gender: "male" | "female" | "unknown";
  birth_date?: Dayjs | null;
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

function maskPhone(phone?: string | null): string {
  if (!phone) return "—";
  if (phone.length >= 7) {
    return `${phone.slice(0, 3)}****${phone.slice(-4)}`;
  }
  if (phone.length <= 2) {
    return "*".repeat(phone.length);
  }
  return `${phone[0]}${"*".repeat(phone.length - 2)}${phone[phone.length - 1]}`;
}

export function PatientListPage() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PatientRow | null>(null);
  const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);
  const [deleteImpactSummary, setDeleteImpactSummary] = useState<string[]>([]);
  const [deleteCheckLoading, setDeleteCheckLoading] = useState(false);
  const [deleteReadyPatientId, setDeleteReadyPatientId] = useState<number | null>(null);
  const deleteCheckRequestIdRef = useRef(0);
  const [form] = Form.useForm<CreatePatientValues>();
  const [editForm] = Form.useForm<EditPatientValues>();

  const { data, isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => {
      const r = await apiClient.get<PatientRow[]>("/patients/");
      return r.data;
    },
  });

  const { data: editingPatient, isLoading: editLoading } = useQuery({
    queryKey: ["patient", editId],
    queryFn: async () => {
      const r = await apiClient.get<PatientDetail>(`/patients/${editId}/`);
      return r.data;
    },
    enabled: editId != null,
  });

  useEffect(() => {
    if (!editingPatient || editId == null) return;
    editForm.setFieldsValue({
      name: editingPatient.name,
      gender: (editingPatient.gender as EditPatientValues["gender"]) ?? "unknown",
      birth_date: editingPatient.birth_date ? dayjs(editingPatient.birth_date) : undefined,
      age: editingPatient.age ?? undefined,
      phone: editingPatient.phone,
      symptom_note: editingPatient.symptom_note ?? "",
    });
  }, [editingPatient, editForm, editId]);

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

  const updateMutation = useMutation({
    mutationFn: async (values: EditPatientValues) => {
      if (editId == null) return;
      await apiClient.patch(`/patients/${editId}/`, {
        name: values.name.trim(),
        gender: values.gender,
        birth_date: values.birth_date ? values.birth_date.format("YYYY-MM-DD") : null,
        age: values.age ?? null,
        phone: values.phone.trim(),
        symptom_note: (values.symptom_note ?? "").trim(),
        is_active: editingPatient?.is_active !== false,
      });
    },
    onSuccess: async () => {
      message.success("已保存");
      setEditId(null);
      editForm.resetFields();
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err: unknown) => message.error(backendDetail(err) ?? "保存失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!deleteTarget) return;
      await apiClient.delete(`/patients/${deleteTarget.id}/`);
    },
    onSuccess: async () => {
      message.success("患者档案已删除");
      setDeleteTarget(null);
      setDeleteBlockedReason(null);
      setDeleteImpactSummary([]);
      setDeleteReadyPatientId(null);
      deleteCheckRequestIdRef.current += 1;
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err: unknown) => {
      setDeleteBlockedReason(backendDetail(err) ?? "删除失败，请稍后重试或联系管理员。");
    },
  });

  const openDeleteModal = async (row: PatientRow) => {
    setDeleteTarget(row);
    setDeleteBlockedReason(null);
    setDeleteImpactSummary([]);
    setDeleteReadyPatientId(null);
    setDeleteCheckLoading(true);
    const requestId = deleteCheckRequestIdRef.current + 1;
    deleteCheckRequestIdRef.current = requestId;
    const isCurrentRequest = () => deleteCheckRequestIdRef.current === requestId;
    try {
      const r = await apiClient.get<unknown[]>(`/studies/project-patients/?patient=${row.id}`);
      if (!isCurrentRequest()) return;
      const linkedCount = r.data.length;
      if (linkedCount > 0) {
        setDeleteReadyPatientId(null);
        setDeleteBlockedReason(
          `该患者仍关联 ${linkedCount} 个研究项目，系统禁止物理删除。需先到项目中删除或解绑该患者。`,
        );
        return;
      }
      setDeleteReadyPatientId(row.id);
      setDeleteImpactSummary([
        "将永久删除该患者档案及本地可恢复副本（若存在），且不可恢复。",
        "当前未检测到研究项目入组关联。",
      ]);
    } catch (err) {
      if (!isCurrentRequest()) return;
      setDeleteReadyPatientId(null);
      setDeleteBlockedReason(backendDetail(err) ?? "删除前检查失败，请稍后重试或联系管理员。");
    } finally {
      if (isCurrentRequest()) {
        setDeleteCheckLoading(false);
      }
    }
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
        columns={[
          {
            title: "姓名",
            dataIndex: "name",
            render: (name: string, row) => <Link to={`/patients/${row.id}`}>{name}</Link>,
          },
          {
            title: "性别",
            dataIndex: "gender",
            render: (v: string) => genderLabel[v] ?? v,
          },
          { title: "年龄", dataIndex: "age" },
          { title: "手机号", dataIndex: "phone", render: (phone: string) => maskPhone(phone) },
          {
            title: "主治医生",
            dataIndex: "primary_doctor_name",
            render: (name: string | null | undefined) => name || "—",
          },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
                <Button type="link" style={{ padding: 0 }} onClick={() => setEditId(row.id)}>
                  编辑
                </Button>
                <Button
                  danger
                  type="link"
                  style={{ padding: 0 }}
                  onClick={() => void openDeleteModal(row)}
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
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

      <Modal
        title="编辑患者"
        open={editId != null}
        onCancel={() => {
          setEditId(null);
          editForm.resetFields();
        }}
        footer={null}
        destroyOnClose
      >
        {editLoading && !editingPatient ? (
          <div>加载中…</div>
        ) : (
          <Form<EditPatientValues>
            form={editForm}
            layout="vertical"
            onFinish={(v) => updateMutation.mutate(v)}
          >
            <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
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
            <Form.Item label="出生日期" name="birth_date">
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="年龄" name="age">
              <InputNumber min={0} max={130} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="手机号" name="phone" rules={[{ required: true, message: "请输入手机号" }]}>
              <Input />
            </Form.Item>
            <Form.Item label="备注" name="symptom_note">
              <Input.TextArea rows={2} />
            </Form.Item>
            <Form.Item label="档案状态">
              <Space direction="vertical" size={0}>
                <Tag color={editingPatient?.is_active !== false ? "green" : "default"}>
                  {editingPatient?.is_active !== false ? "启用" : "已停用"}
                </Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  停用或删除请在患者详情页操作（须二次确认）。
                </Typography.Text>
              </Space>
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                  保存
                </Button>
                <Button
                  onClick={() => {
                    setEditId(null);
                    editForm.resetFields();
                  }}
                >
                  取消
                </Button>
              </Space>
            </Form.Item>
          </Form>
        )}
      </Modal>
      <DestructiveActionModal
        open={deleteTarget != null}
        title="确认删除患者档案？"
        okText="删除"
        impactSummary={deleteImpactSummary}
        blockedReason={deleteBlockedReason}
        confirmLoading={deleteCheckLoading || deleteMutation.isPending}
        onCancel={() => {
          setDeleteTarget(null);
          setDeleteBlockedReason(null);
          setDeleteImpactSummary([]);
          setDeleteReadyPatientId(null);
          deleteCheckRequestIdRef.current += 1;
        }}
        onConfirm={() => {
          if (
            !deleteTarget ||
            deleteReadyPatientId !== deleteTarget.id ||
            deleteBlockedReason ||
            deleteCheckLoading
          ) {
            return;
          }
          void deleteMutation.mutateAsync().catch(() => undefined);
        }}
      />
    </Card>
  );
}
