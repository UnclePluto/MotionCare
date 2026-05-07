import { Button, Card, Space, Table } from "antd";

export function PatientListPage() {
  return (
    <Card title="患者档案" extra={<Button type="primary">新建患者</Button>}>
      <Table
        rowKey="id"
        dataSource={[]}
        columns={[
          { title: "姓名", dataIndex: "name" },
          { title: "性别", dataIndex: "gender" },
          { title: "年龄", dataIndex: "age" },
          { title: "手机号", dataIndex: "phone" },
          {
            title: "操作",
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

