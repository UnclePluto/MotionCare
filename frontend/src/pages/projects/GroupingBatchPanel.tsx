import { Alert, Button, Card, Space, Table } from "antd";

export function GroupingBatchPanel() {
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Alert
        type="info"
        message="从全局患者列表选择患者加入项目后，系统会按项目分组比例生成随机分组草案。确认前可调整，确认后不可修改。"
      />
      <Card title="待确认分组草案" extra={<Button type="primary">确认分组</Button>}>
        <Table
          rowKey="id"
          dataSource={[]}
          columns={[
            { title: "患者", dataIndex: "patientName" },
            { title: "当前分组", dataIndex: "groupName" },
            { title: "操作", render: () => <Button type="link">调整</Button> },
          ]}
        />
      </Card>
    </Space>
  );
}

