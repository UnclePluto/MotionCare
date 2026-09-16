import { Button, Table, Tag, Typography } from "antd";
import type { MotionSessionSummary, TrackingRecentRecord } from "./types";

const labels = { partial: "部分完成", awaiting_upload: "运动已做完，视频待上传", completed: "已完成" };

export function MotionSessionsPanel({ sessions, records, onOpen }: {
  sessions: MotionSessionSummary[];
  records: TrackingRecentRecord[];
  onOpen: (record: TrackingRecentRecord) => void;
}) {
  return <Table<MotionSessionSummary> rowKey="id" dataSource={sessions} pagination={{ pageSize: 10 }}
    locale={{ emptyText: "暂无按组运动记录" }} scroll={{ x: 720 }}
    columns={[
      { title: "运动日期", dataIndex: "training_date" },
      { title: "动作", dataIndex: "action_name" },
      { title: "目标", render: (_, s) => `${s.count_unit === "per_side" ? "每侧" : "每组"} ${s.repetitions} 个 × ${s.planned_sets} 组` },
      { title: "已做完", render: (_, s) => `${s.completed_sets}/${s.planned_sets} 组` },
      { title: "已上传", render: (_, s) => `${s.uploaded_sets}/${s.planned_sets} 组` },
      { title: "状态", render: (_, s) => <Tag>{labels[s.status]}</Tag> },
      { title: "实际运动时长", render: (_, s) => `${s.actual_duration_seconds} 秒` },
    ]}
    expandable={{ expandedRowRender: session => <>
      {session.count_unit === "per_side" && <Typography.Paragraph>目标为左右每侧个数，分析结果为双侧合计。</Typography.Paragraph>}
      <Table rowKey="index" dataSource={session.sets} pagination={false} size="small" columns={[
        { title: "组序号", render: (_, group) => `${group.index}/${session.planned_sets} 组` },
        { title: "完成情况", render: (_, group) => group.completed ? "本组已做完" : "未完成" },
        { title: "录像", render: (_, group) => group.uploaded ? "已上传" : group.completed ? "待上传" : "无正式录像" },
        { title: "分析个数", render: (_, group) => records.find(r => r.video_id === group.video_id && group.video_id != null)?.motion_total_count ?? "—" },
        { title: "查看", render: (_, group) => {
          const record = records.find(r => group.video_id != null && r.video_id === group.video_id);
          return record && group.uploaded ? <Button onClick={() => onOpen(record)}>视频、分析与健康曲线</Button> : "—";
        } },
      ]} />
    </> }} />;
}
