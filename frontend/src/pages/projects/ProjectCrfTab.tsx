import { useQuery } from "@tanstack/react-query";
import { Button, Card, Select, Space, Typography } from "antd";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../../api/client";

type ProjectPatientOption = {
  id: number;
  patient_name: string;
  patient_phone: string;
};

type Props = {
  projectId: number;
};

export function ProjectCrfTab({ projectId }: Props) {
  const navigate = useNavigate();
  const [projectPatientId, setProjectPatientId] = useState<number | undefined>();

  const { data, isLoading } = useQuery({
    queryKey: ["project-patients", projectId],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientOption[]>(
        "/studies/project-patients/",
        { params: { project: projectId } },
      );
      return r.data;
    },
  });

  const options = useMemo(
    () =>
      (data ?? []).map((p) => ({
        value: p.id,
        label: `${p.patient_name}（${p.patient_phone}）`,
      })),
    [data],
  );

  const openPreview = () => {
    if (!projectPatientId) return;
    navigate(`/crf?projectPatientId=${projectPatientId}`);
  };

  return (
    <Card title="CRF 报告">
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Typography.Paragraph type="secondary">
          选择本项目下的「项目患者」记录，跳转到 CRF 预览页查看聚合结果并导出 DOCX。
        </Typography.Paragraph>
        <Space wrap>
          <Select
            style={{ minWidth: 320 }}
            placeholder="选择项目患者"
            loading={isLoading}
            options={options}
            value={projectPatientId}
            onChange={setProjectPatientId}
            allowClear
            showSearch
            optionFilterProp="label"
          />
          <Button type="primary" disabled={!projectPatientId} onClick={openPreview}>
            打开预览
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
