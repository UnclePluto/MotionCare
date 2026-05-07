import { Alert, Button, Card, Form, Input, Select } from "antd";

export function TrainingEntryPage() {
  return (
    <Card title="后台代患者录入训练">
      <Alert
        type="warning"
        showIcon
        message="第一版只能基于当前生效处方录入训练，不支持旧处方历史补录。"
        style={{ marginBottom: 16 }}
      />
      <Form layout="vertical">
        <Form.Item label="当前处方动作" name="prescriptionAction">
          <Select options={[]} placeholder="请选择当前处方动作" />
        </Form.Item>
        <Form.Item label="训练日期" name="trainingDate">
          <Input placeholder="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item label="完成状态" name="status">
          <Select
            options={[
              { label: "已完成", value: "completed" },
              { label: "部分完成", value: "partial" },
              { label: "未完成", value: "missed" },
            ]}
          />
        </Form.Item>
        <Button type="primary">保存训练记录</Button>
      </Form>
    </Card>
  );
}

