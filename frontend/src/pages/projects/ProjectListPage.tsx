import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Modal, Space, Table, message } from "antd";
import { isAxiosError } from "axios";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type ProjectRow = {
  id: number;
  name: string;
  status: string;
  patient_count?: number;
};

const statusLabel: Record<string, string> = {
  draft: "草稿",
  active: "进行中",
  archived: "已归档",
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

export function ProjectListPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; description?: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<ProjectRow[]>("/studies/projects/");
      return r.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (values: { name: string; description?: string }) => {
      await apiClient.post("/studies/projects/", {
        name: values.name.trim(),
        description: (values.description ?? "").trim(),
        crf_template_version: "1.1",
        visit_plan: [],
        status: "draft",
      });
    },
    onSuccess: async () => {
      message.success("项目已创建");
      setOpen(false);
      form.resetFields();
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: () => message.error("创建失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: async (projectId: number) => {
      await apiClient.delete(`/studies/projects/${projectId}/`);
    },
    onSuccess: async () => {
      message.success("项目已删除");
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: (err: unknown) => message.error(backendDetail(err) ?? "删除失败"),
  });

  const confirmDelete = (row: ProjectRow) => {
    Modal.confirm({
      title: `确认删除项目「${row.name}」？`,
      content: "若项目中仍有患者或存在待确认分组批次，系统将拒绝删除。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: () => deleteMutation.mutateAsync(row.id),
    });
  };

  return (
    <Card
      title="研究项目"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          新建项目
        </Button>
      }
    >
      <Table<ProjectRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          {
            title: "项目名称",
            dataIndex: "name",
            render: (text: string) => text,
          },
          {
            title: "状态",
            dataIndex: "status",
            render: (v: string) => statusLabel[v] ?? v,
          },
          {
            title: "患者数",
            dataIndex: "patient_count",
            render: (n: number | undefined) => (typeof n === "number" ? n : "—"),
          },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
                <Link to={`/projects/${row.id}`}>详情</Link>
                <Button type="link" danger style={{ padding: 0 }} onClick={() => confirmDelete(row)}>
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title="新建研究项目"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item
            label="项目名称"
            name="name"
            rules={[{ required: true, message: "请输入项目名称" }]}
          >
            <Input placeholder="项目名称" />
          </Form.Item>
          <Form.Item label="描述（可选）" name="description">
            <Input.TextArea rows={3} placeholder="简要描述" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
                创建
              </Button>
              <Button onClick={() => setOpen(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
