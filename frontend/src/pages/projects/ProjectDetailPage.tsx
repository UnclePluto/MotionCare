import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Tabs, Typography } from "antd";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { GroupingBatchPanel } from "./GroupingBatchPanel";
import { ProjectCrfTab } from "./ProjectCrfTab";
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
    <Card loading={isLoading} title={project ? project.name : "项目详情"}>
      {project && (
        <Typography.Paragraph type="secondary">
          CRF 模板版本：{project.crf_template_version} · 状态：
          {statusLabel[project.status] ?? project.status}
          {project.description ? ` · ${project.description}` : ""}
        </Typography.Paragraph>
      )}
      <Tabs
        items={[
          {
            key: "groups",
            label: "项目分组",
            children: <ProjectGroupsTab projectId={id} />,
          },
          {
            key: "patients",
            label: "项目患者",
            children: <ProjectPatientsTab projectId={id} />,
          },
          {
            key: "grouping",
            label: "随机分组",
            children: <GroupingBatchPanel projectId={id} />,
          },
          {
            key: "crf",
            label: "CRF 报告",
            children: <ProjectCrfTab projectId={id} />,
          },
        ]}
      />
    </Card>
  );
}
