import { useQuery } from "@tanstack/react-query";
import { Button, Card, Space, Table } from "antd";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type ProjectPatientRow = {
  id: number;
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  grouping_batch: number | null;
  grouping_status: string;
};

const groupingLabel: Record<string, string> = {
  pending: "待确认",
  confirmed: "已确认",
};

type Props = {
  projectId: number;
};

export function ProjectPatientsTab({ projectId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["project-patients", projectId],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>(
        "/studies/project-patients/",
        { params: { project: projectId } },
      );
      return r.data;
    },
  });

  return (
    <Card title="项目患者">
      <Table<ProjectPatientRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          { title: "姓名", dataIndex: "patient_name" },
          { title: "手机号", dataIndex: "patient_phone" },
          {
            title: "当前分组",
            dataIndex: "group_name",
            render: (v: string | null) => v ?? "—",
          },
          {
            title: "分组状态",
            dataIndex: "grouping_status",
            render: (v: string) => groupingLabel[v] ?? v,
          },
          {
            title: "操作",
            key: "actions",
            render: (_, row) => (
              <Space>
                <Link to={`/crf?projectPatientId=${row.id}`}>CRF</Link>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
