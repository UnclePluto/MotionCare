import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Drawer, Space, Tag, message } from "antd";
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
import {
  ProjectGroupingBoard,
  type ProjectGroupingBoardActionState,
  type ProjectGroupingBoardHandle,
} from "./ProjectGroupingBoard";
import { ProjectGroupsTab } from "./ProjectGroupsTab";

type StudyProject = {
  id: number;
  name: string;
  description: string;
  crf_template_version: string;
  status: "draft" | "active" | "archived";
};

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const qc = useQueryClient();
  const boardRef = useRef<ProjectGroupingBoardHandle>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [groupRevision, setGroupRevision] = useState(0);
  const [boardState, setBoardState] = useState<ProjectGroupingBoardActionState>({
    hasActiveGroups: false,
    hasEligibleSelection: false,
    confirmLoading: false,
  });

  const { data: project, isLoading, isError } = useQuery({
    queryKey: ["study-project", id],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject>(`/studies/projects/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const completeMutation = useMutation({
    mutationFn: async () => {
      const r = await apiClient.post<Partial<StudyProject>>(`/studies/projects/${id}/complete/`);
      return r.data;
    },
    onSuccess: async (completedProject) => {
      message.success("项目已完结");
      setCompleteOpen(false);
      qc.setQueryData<StudyProject>(["study-project", id], (prev) => {
        if (!prev) return prev;
        return { ...prev, ...completedProject, status: "archived" };
      });
      boardRef.current?.clearDraft();
      await qc.invalidateQueries({ queryKey: ["study-project", id], refetchType: "none" });
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: () => {
      message.error("项目完结失败");
    },
  });

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的项目 ID" />;
  }

  if (isError) {
    return <Alert type="error" message="项目不存在或无权限访问" />;
  }

  const isCompleted = project?.status === "archived";

  return (
    <Card
      loading={isLoading}
      title={project ? project.name : "项目详情"}
      extra={
        <Space>
          {isCompleted ? <Tag>已完结</Tag> : null}
          <Button
            type="default"
            disabled={isCompleted || !boardState.hasEligibleSelection || !boardState.hasActiveGroups}
            onClick={() => boardRef.current?.randomize()}
          >
            随机分组
          </Button>
          <Button
            type="primary"
            disabled={isCompleted || !boardState.hasActiveGroups}
            loading={boardState.confirmLoading}
            onClick={() => boardRef.current?.confirm()}
          >
            确认分组
          </Button>
          <Button type="default" disabled={isCompleted} onClick={() => setConfigOpen(true)}>
            新增分组
          </Button>
          <Button danger disabled={isCompleted} onClick={() => setCompleteOpen(true)}>
            项目完结
          </Button>
        </Space>
      }
    >
      {project && (
        <>
          <ProjectGroupingBoard
            ref={boardRef}
            projectId={id}
            groupRevision={groupRevision}
            readOnly={isCompleted}
            onActionStateChange={setBoardState}
          />
          <Drawer
            title="分组配置（元数据）"
            width={720}
            open={configOpen}
            onClose={() => setConfigOpen(false)}
            destroyOnClose
          >
            <ProjectGroupsTab
              projectId={id}
              onGroupCreated={() => setGroupRevision((value) => value + 1)}
              readOnly={isCompleted}
            />
          </Drawer>
          <DestructiveActionModal
            open={completeOpen}
            title={`确认完结研究项目「${project.name}」？`}
            okText="确认完结"
            impactSummary={[
              "项目完结后，分组、解绑、随机和确认等项目内操作将变为只读。",
              "已生成的访视、CRF 与患者入组记录保留用于后续查询和导出。",
            ]}
            confirmLoading={completeMutation.isPending}
            onCancel={() => setCompleteOpen(false)}
            onConfirm={() => void completeMutation.mutateAsync()}
          />
        </>
      )}
    </Card>
  );
}
