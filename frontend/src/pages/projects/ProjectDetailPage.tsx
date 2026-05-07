import { Card, Tabs } from "antd";
import { GroupingBatchPanel } from "./GroupingBatchPanel";

export function ProjectDetailPage() {
  return (
    <Card title="项目详情">
      <Tabs
        items={[
          { key: "groups", label: "项目分组", children: <div>分组配置</div> },
          { key: "patients", label: "项目患者", children: <div>患者列表</div> },
          { key: "grouping", label: "随机分组", children: <GroupingBatchPanel /> },
          { key: "crf", label: "CRF 报告", children: <div>CRF 报告</div> },
        ]}
      />
    </Card>
  );
}

