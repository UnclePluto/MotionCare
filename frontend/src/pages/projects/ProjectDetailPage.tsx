import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Drawer, Space, Tabs, Typography } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { ProjectGroupingBoard } from "./ProjectGroupingBoard";
import { ProjectGroupsTab } from "./ProjectGroupsTab";
import { ProjectPatientsTab } from "./ProjectPatientsTab";

type StudyProject = {
  id: number;
  name: string;
  description: string;
  crf_template_version: string;
  status: string;
};

const statusLabel: Record<string, string> = {
  draft: "草稿",
  active: "进行中",
  archived: "已归档",
};

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const [configOpen, setConfigOpen] = useState(false);

  const { data: project, isLoading, isError } = useQuery({
    queryKey: ["study-project", id],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject>(`/studies/projects/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的项目 ID" />;
  }

  if (isError) {
    return <Alert type="error" message="项目不存在或无权限访问" />;
  }

  return (
    <Card
      loading={isLoading}
      title={project ? project.name : "项目详情"}
      extra={
        <Space>
          <Button type="default" onClick={() => setConfigOpen(true)}>
            新增分组 / 元数据
          </Button>
        </Space>
      }
    >
      {project && (
        <>
          <Typography.Paragraph type="secondary">
            CRF 模板版本：{project.crf_template_version} · 状态：
            {statusLabel[project.status] ?? project.status}
            {project.description ? ` · ${project.description}` : ""}
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            CRF 录入请从「患者详情」对应项目行进入；访视评估可从「项目患者」页 T0/T1/T2 进入。
          </Typography.Paragraph>
          <Tabs
            items={[
              {
                key: "board",
                label: "分组看板",
                children: <ProjectGroupingBoard projectId={id} />,
              },
              {
                key: "patients",
                label: "项目患者",
                children: <ProjectPatientsTab projectId={id} />,
              },
            ]}
          />
          <Drawer
            title="分组配置（元数据）"
            width={720}
            open={configOpen}
            onClose={() => setConfigOpen(false)}
            destroyOnClose
          >
            <ProjectGroupsTab projectId={id} />
          </Drawer>
        </>
      )}
    </Card>
  );
}
