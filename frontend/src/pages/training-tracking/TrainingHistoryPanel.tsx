import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Skeleton, Space, Table, Typography } from "antd";
import { apiClient } from "../../api/client";
import type { LatestMotionAnalysisJob } from "./types";

type HistoryRecord = {
  id: number;
  action_name: string;
  training_date: string;
  invalidated_at: string;
  invalidation_reason: string;
  cutover_marker: string;
  video_id: number | null;
  motion_total_count: number | null;
  motion_standard_count: number | null;
  motion_nonstandard_count: number | null;
};

function HistoryVideo({ videoId }: { videoId: number }) {
  const queryClient = useQueryClient();
  const [opened, setOpened] = useState(false);
  const original = useQuery({
    queryKey: ["training-history-video", videoId],
    queryFn: async () => (await apiClient.get<{ url: string }>(`/training/videos/${videoId}/download-url/`)).data,
    enabled: opened,
    staleTime: 0,
  });
  const analysis = useQuery({
    queryKey: ["training-history-analysis", videoId],
    queryFn: async () => (await apiClient.get<LatestMotionAnalysisJob | null>(`/training/videos/${videoId}/analysis-jobs/latest/`)).data,
    enabled: opened,
    refetchInterval: query => ["pending", "running"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  useEffect(() => {
    if (analysis.data?.status === "succeeded" || analysis.data?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["training-history"] });
    }
  }, [analysis.data?.status, queryClient]);
  const labels = { pending: "待分析", running: "分析中", succeeded: "分析成功", failed: "分析失败" };
  return <Space direction="vertical">
    <Button onClick={() => setOpened(!opened)} aria-expanded={opened}>{opened ? "关闭历史录像" : "查看历史录像"}</Button>
    {opened && <>
      {original.isLoading ? <Skeleton active /> : original.isError ? <Alert type="error" message="原始视频加载失败" action={<Button onClick={() => void original.refetch()}>重试视频</Button>} /> : original.data && <video aria-label="历史训练原始视频" controls preload="metadata" src={original.data.url} style={{ width: "100%", maxWidth: 480 }} />}
      {analysis.isError ? <Alert type="error" message="分析状态加载失败" action={<Button onClick={() => void analysis.refetch()}>重试分析状态</Button>} /> : <Typography.Text>{analysis.isLoading ? "正在读取分析状态" : analysis.data ? labels[analysis.data.status] : "暂无分析结果"}</Typography.Text>}
    </>}
  </Space>;
}

export function TrainingHistoryPanel({ projectPatientId }: { projectPatientId: number }) {
  const [opened, setOpened] = useState(false);
  const history = useQuery({
    queryKey: ["training-history", projectPatientId],
    queryFn: async () => (await apiClient.get<HistoryRecord[]>("/training/history/", { params: { project_patient: projectPatientId } })).data,
    enabled: opened,
  });
  return <Space direction="vertical" style={{ width: "100%" }}>
    <Button onClick={() => setOpened(!opened)} aria-expanded={opened}>{opened ? "收起作废训练历史" : "查看作废训练历史"}</Button>
    {opened && <>
      <Typography.Paragraph>作废记录仅供历史备查，不计入正常训练统计和导出。</Typography.Paragraph>
      {history.isError ? <Alert type="error" showIcon message="历史记录加载失败，请检查访问权限后重试" action={<Button onClick={() => void history.refetch()}>重试加载</Button>} /> : <Table<HistoryRecord>
        rowKey="id" loading={history.isLoading} dataSource={history.data ?? []} pagination={{ pageSize: 10 }} scroll={{ x: 800 }}
        locale={{ emptyText: "当前项目暂无作废训练记录" }}
        columns={[
          { title: "训练日期", dataIndex: "training_date" },
          { title: "动作", dataIndex: "action_name" },
          { title: "作废时间", dataIndex: "invalidated_at", render: (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) },
          { title: "作废原因", dataIndex: "invalidation_reason" },
          { title: "历史录像", render: (_, row) => row.video_id ? <HistoryVideo key={row.id} videoId={row.video_id} /> : "无录像" },
          { title: "总次数 / 标准 / 非标准", render: (_, row) => [row.motion_total_count, row.motion_standard_count, row.motion_nonstandard_count].map(value => value ?? "—").join(" / ") },
        ]}
      />}
    </>}
  </Space>;
}
