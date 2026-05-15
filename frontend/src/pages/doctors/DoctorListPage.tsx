import { useQuery } from "@tanstack/react-query";
import { Button, Card, Space, Table } from "antd";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../../api/client";
import { maskPhoneForList } from "../patients/phoneMask";
import { formatDoctorDateTime } from "./doctorUtils";
import type { Doctor } from "./types";

export function DoctorListPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["doctors"],
    queryFn: async () => {
      const r = await apiClient.get<Doctor[]>("/accounts/users/");
      return r.data;
    },
  });

  return (
    <Card
      title="医生管理"
      extra={
        <Button type="primary" onClick={() => navigate("/doctors/new")}>
          添加医生
        </Button>
      }
    >
      <Table<Doctor>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          { title: "医生姓名", dataIndex: "name" },
          { title: "手机号", dataIndex: "phone", render: (v: string) => maskPhoneForList(v ?? "") },
          { title: "创建时间", dataIndex: "date_joined", render: (v: string) => formatDoctorDateTime(v) },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
                <Button type="link" style={{ padding: 0 }} onClick={() => navigate(`/doctors/${row.id}/edit`)}>
                  编辑
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
