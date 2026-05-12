import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Modal, Space, Table, message } from "antd";
import { isAxiosError } from "axios";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { DestructiveActionModal } from "../components/DestructiveActionModal";

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
  const [deleteTarget, setDeleteTarget] = useState<ProjectRow | null>(null);
  const [deleteApiBlocked, setDeleteApiBlocked] = useState<string | null>(null);

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
      setDeleteTarget(null);
      setDeleteApiBlocked(null);
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: (err: unknown) => {
      setDeleteApiBlocked(backendDetail(err) ?? "删除失败，请稍后重试。");
    },
  });

  const openDeleteModal = (row: ProjectRow) => {
    setDeleteApiBlocked(null);
    setDeleteTarget(row);
  };

  const deleteClientBlocked =
    deleteTarget &&
    typeof deleteTarget.patient_count === "number" &&
    deleteTarget.patient_count > 0
      ? `该项目仍有 ${deleteTarget.patient_count} 名入组患者，系统禁止删除。请先在项目详情分组看板将患者解绑。`
      : null;

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
                <Button type="link" danger style={{ padding: 0 }} onClick={() => openDeleteModal(row)}>
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

      <DestructiveActionModal
        open={deleteTarget != null}
        title={deleteTarget ? `确认删除研究项目「${deleteTarget.name}」？` : "确认删除？"}
        okText="删除"
        impactSummary={
          deleteTarget
            ? [
                `将请求永久删除研究项目「${deleteTarget.name}」及其在项目维度的配置数据（以服务端实际级联为准）。`,
                typeof deleteTarget.patient_count === "number"
                  ? `当前列表显示该项目下共有 ${deleteTarget.patient_count} 名入组患者；若有任意入组关系，系统将拒绝删除。`
                  : "若仍存在患者入组关系，系统将拒绝删除。",
                "请先在项目详情分组看板移除已确认入组患者，再删除项目。",
              ]
            : []
        }
        blockedReason={deleteClientBlocked ?? deleteApiBlocked}
        confirmLoading={deleteMutation.isPending}
        onCancel={() => {
          setDeleteTarget(null);
          setDeleteApiBlocked(null);
        }}
        onConfirm={() => {
          if (!deleteTarget || deleteClientBlocked) return;
          void deleteMutation.mutateAsync(deleteTarget.id);
        }}
      />
    </Card>
  );
}
