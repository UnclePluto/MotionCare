import { Button, Card, Form, InputNumber } from "antd";

export function DailyHealthPage() {
  return (
    <Card title="每日健康数据">
      <Form layout="vertical">
        <Form.Item label="步数" name="steps">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="运动时长（分钟）" name="exerciseMinutes">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="平均心率" name="averageHeartRate">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="最高心率" name="maxHeartRate">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="最低心率" name="minHeartRate">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="睡眠时长（小时）" name="sleepHours">
          <InputNumber min={0} step={0.5} style={{ width: "100%" }} />
        </Form.Item>
        <Button type="primary">保存健康数据</Button>
      </Form>
    </Card>
  );
}

