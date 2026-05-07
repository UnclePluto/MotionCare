import { Alert, Button, Card, Table } from "antd";

export function PrescriptionPanel() {
  return (
    <Card title="处方管理" extra={<Button type="primary">新建处方版本</Button>}>
      <Alert
        type="info"
        showIcon
        message="处方属于项目患者。调整处方会生成新版本；旧版本归档；训练录入只使用当前生效处方。"
        style={{ marginBottom: 16 }}
      />
      <Table
        rowKey="id"
        dataSource={[]}
        columns={[
          { title: "版本", dataIndex: "version" },
          { title: "状态", dataIndex: "status" },
          { title: "开设医生", dataIndex: "openedBy" },
          { title: "生效时间", dataIndex: "effectiveAt" },
        ]}
      />
    </Card>
  );
}

