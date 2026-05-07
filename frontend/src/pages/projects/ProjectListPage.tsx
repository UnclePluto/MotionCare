import { Button, Card, Table } from "antd";

export function ProjectListPage() {
  return (
    <Card title="研究项目" extra={<Button type="primary">新建项目</Button>}>
      <Table
        rowKey="id"
        dataSource={[]}
        columns={[
          { title: "项目名称", dataIndex: "name" },
          { title: "CRF 模板", dataIndex: "crfTemplateVersion" },
          { title: "状态", dataIndex: "status" },
          { title: "患者数", dataIndex: "patientCount" },
        ]}
      />
    </Card>
  );
}

