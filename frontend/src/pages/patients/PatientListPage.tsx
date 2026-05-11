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
  Switch,
  Table,
  message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { isAxiosError } from "axios";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

type PatientRow = {
  id: number;
  name: string;
  gender: string;
  age: number | null;
  phone: string;
  primary_doctor: number | null;
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
  is_active: boolean;
};

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  if ("detail" in data && typeof (data as { detail?: unknown }).detail === "string") {
    return (data as { detail: string }).detail;
  }
  return null;
}

export function PatientListPage() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
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
      is_active: editingPatient.is_active !== false,
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
        is_active: values.is_active,
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
          { title: "姓名", dataIndex: "name" },
          {
            title: "性别",
            dataIndex: "gender",
            render: (v: string) => genderLabel[v] ?? v,
          },
          { title: "年龄", dataIndex: "age" },
          { title: "手机号", dataIndex: "phone" },
          {
            title: "主治医生 ID",
            dataIndex: "primary_doctor",
            render: (pid: number | null) => pid ?? "—",
          },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
                <Button type="link" style={{ padding: 0 }} onClick={() => setEditId(row.id)}>
                  编辑
                </Button>
                <Link to={`/patients/${row.id}`}>详情</Link>
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
            <Form.Item label="档案启用" name="is_active" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
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
    </Card>
  );
}
