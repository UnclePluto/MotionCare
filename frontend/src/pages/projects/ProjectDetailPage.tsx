import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Drawer, Space } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { ProjectGroupingBoard } from "./ProjectGroupingBoard";
import { ProjectGroupsTab } from "./ProjectGroupsTab";

type StudyProject = {
  id: number;
  name: string;
  description: string;
  crf_template_version: string;
  status: string;
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
            新增分组
          </Button>
        </Space>
      }
    >
      {project && (
        <>
          <ProjectGroupingBoard projectId={id} />
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
