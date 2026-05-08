import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, InputNumber, Modal, Space, Switch, Table, message } from "antd";
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
};

export function ProjectGroupsTab({ projectId }: Props) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; target_ratio: number }>();

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
    mutationFn: async (values: { name: string; target_ratio: number }) => {
      await apiClient.post("/studies/groups/", {
        project: projectId,
        name: values.name.trim(),
        description: "",
        target_ratio: values.target_ratio,
        sort_order: (data?.length ?? 0),
        is_active: true,
      });
    },
    onSuccess: async () => {
      message.success("分组已创建");
      setOpen(false);
      form.resetFields();
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
    },
    onError: () => message.error("创建失败"),
  });

  return (
    <Card
      title="分组配置"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
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
          { title: "目标比例", dataIndex: "target_ratio", width: 120 },
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
          initialValues={{ target_ratio: 1 }}
          onFinish={(v) => createMutation.mutate(v)}
        >
          <Form.Item
            label="分组名称"
            name="name"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="例如：干预组" />
          </Form.Item>
          <Form.Item
            label="目标比例"
            name="target_ratio"
            rules={[{ required: true, message: "请输入比例" }]}
          >
            <InputNumber min={1} style={{ width: "100%" }} />
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
