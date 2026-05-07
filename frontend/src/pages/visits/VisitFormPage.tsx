import { Button, Card, Form, Input, Radio, Space } from "antd";

export function VisitFormPage() {
  return (
    <Card title="访视表单">
      <Form layout="vertical">
        <Form.Item label="访视状态" name="status">
          <Radio.Group>
            <Radio value="draft">草稿</Radio>
            <Radio value="completed">已完成</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item label="访视日期" name="visitDate">
          <Input placeholder="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item label="表单数据" name="formData">
          <Input.TextArea rows={8} placeholder="第一版按 CRF 章节拆分具体字段" />
        </Form.Item>
        <Space>
          <Button type="primary">保存</Button>
          <Button>返回</Button>
        </Space>
      </Form>
    </Card>
  );
}

