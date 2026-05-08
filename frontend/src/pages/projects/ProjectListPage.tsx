import { useQuery } from "@tanstack/react-query";
import { Button, Card, Table } from "antd";

import { apiClient } from "../../api/client";

type ProjectRow = {
  id: number;
  name: string;
  crf_template_version: string;
  status: string;
};

const statusLabel: Record<string, string> = {
  draft: "草稿",
  active: "进行中",
  archived: "已归档",
};

export function ProjectListPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<ProjectRow[]>("/studies/projects/");
      return r.data;
    },
  });

  return (
    <Card title="研究项目" extra={<Button type="primary">新建项目</Button>}>
      <Table<ProjectRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          { title: "项目名称", dataIndex: "name" },
          { title: "CRF 模板", dataIndex: "crf_template_version" },
          {
            title: "状态",
            dataIndex: "status",
            render: (v: string) => statusLabel[v] ?? v,
          },
          {
            title: "患者数",
            key: "patientCount",
            render: () => "—",
          },
        ]}
      />
    </Card>
  );
}
