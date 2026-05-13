import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Modal, Space, Table, message } from "antd";
import { useState } from "react";

import { apiClient } from "../../api/client";

type StudyGroupRow = {
  id: number;
  project: number;
  name: string;
  description: string;
  target_ratio: number;
  sort_order: number;
  is_active: boolean;
};

type Props = {
  projectId: number;
  onGroupCreated?: () => void;
  readOnly?: boolean;
};

export function ProjectGroupsTab({ projectId, onGroupCreated, readOnly = false }: Props) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ name: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["study-groups", projectId],
    queryFn: async () => {
      const r = await apiClient.get<StudyGroupRow[]>("/studies/groups/", {
        params: { project: projectId },
      });
      return r.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (values: { name: string }) => {
      await apiClient.post("/studies/groups/", {
        project: projectId,
        name: values.name.trim(),
        description: "",
        sort_order: (data?.length ?? 0),
        is_active: true,
      });
    },
    onSuccess: async () => {
      message.success("分组已创建");
      setOpen(false);
      form.resetFields();
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
      onGroupCreated?.();
    },
    onError: () => message.error("创建失败"),
  });

  return (
    <Card
      title="分组配置"
      extra={
        <Button type="primary" disabled={readOnly} onClick={() => setOpen(true)}>
          新建分组
        </Button>
      }
    >
      <Table<StudyGroupRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "已保存占比", dataIndex: "target_ratio", width: 120, render: (v: number) => `${v}%` },
          { title: "排序", dataIndex: "sort_order", width: 100 },
          {
            title: "启用",
            dataIndex: "is_active",
            width: 100,
            render: (v: boolean) => (v ? "是" : "否"),
          },
        ]}
      />
      <Modal
        title="新建分组"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{}}
          onFinish={(v) => {
            if (readOnly) return;
            createMutation.mutate(v);
          }}
        >
          <Form.Item
            label="分组名称"
            name="name"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="例如：干预组" disabled={readOnly} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={createMutation.isPending} disabled={readOnly}>
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
