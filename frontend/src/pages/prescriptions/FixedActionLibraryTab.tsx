import { Badge, Card, Empty, List, Space, Tag, Typography } from "antd";

import type { ActionLibraryItem } from "./types";
import { weeklyFrequencyLabel } from "./prescriptionUtils";

type Props = {
  actions: ActionLibraryItem[];
};

export function FixedActionLibraryTab({ actions }: Props) {
  if (actions.length === 0) {
    return <Empty description="暂无固定动作" />;
  }

  return (
    <List
      grid={{ gutter: 12, xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }}
      dataSource={actions}
      renderItem={(action) => (
        <List.Item>
          <Card size="small" title={action.name}>
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Space wrap size={[8, 8]}>
                <Tag>{action.action_type}</Tag>
                <Tag>{weeklyFrequencyLabel(action.suggested_frequency)}</Tag>
                <Tag>
                  {action.suggested_duration_minutes ? `${action.suggested_duration_minutes} 分钟` : "未配置时长"}
                </Tag>
                <Badge status={action.video_url ? "success" : "default"} text={action.video_url ? "已配置视频" : "视频待配置"} />
                {action.has_ai_supervision ? <Tag color="blue">支持 AI 监督</Tag> : <Tag>无 AI 监督</Tag>}
              </Space>
              <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
                {action.instruction_text || "暂无动作说明"}
              </Typography.Paragraph>
            </Space>
          </Card>
        </List.Item>
      )}
    />
  );
}
