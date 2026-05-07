import { Alert, Button, Card, List, Space } from "antd";

export function CrfPreviewPage() {
  const missingFields: string[] = [];
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title="CRF 预览">
        <Alert
          type="info"
          showIcon
          message="第一版允许带缺失字段导出。缺失字段在预览中提示，导出文件中留空。"
        />
      </Card>
      <Card title="缺失字段">
        <List
          dataSource={missingFields}
          locale={{ emptyText: "暂无缺失字段" }}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>
      <Space>
        <Button type="primary">导出 DOCX</Button>
        <Button>导出 PDF</Button>
      </Space>
    </Space>
  );
}

