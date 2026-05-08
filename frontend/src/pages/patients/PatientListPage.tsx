import { useQuery } from "@tanstack/react-query";
import { Button, Card, Space, Table } from "antd";

import { apiClient } from "../../api/client";

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

export function PatientListPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => {
      const r = await apiClient.get<PatientRow[]>("/patients/");
      return r.data;
    },
  });

  return (
    <Card title="患者档案" extra={<Button type="primary">新建患者</Button>}>
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
            render: () => (
              <Space>
                <Button type="link">详情</Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
