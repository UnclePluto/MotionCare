import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, message } from "antd";
import { useState } from "react";
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

export function PatientListPage() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<CreatePatientValues>();

  const { data, isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => {
      const r = await apiClient.get<PatientRow[]>("/patients/");
      return r.data;
    },
  });

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
    onError: (err: { response?: { data?: Record<string, unknown> } }) => {
      const detail = err.response?.data;
      message.error(
        typeof detail === "object" && detail && "detail" in detail
          ? String(detail.detail)
          : "创建失败（手机号可能已存在）",
      );
    },
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
            render: (id: number | null) => id ?? "—",
          },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
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
    </Card>
  );
}
