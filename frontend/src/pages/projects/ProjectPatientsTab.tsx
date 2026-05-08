import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Modal, Select, Space, Table, message } from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type ProjectPatientRow = {
  id: number;
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  grouping_batch: number | null;
  grouping_status: string;
  visit_ids?: { T0?: number; T1?: number; T2?: number };
};

const groupingLabel: Record<string, string> = {
  pending: "待确认",
  confirmed: "已确认",
};

type Props = {
  projectId: number;
};

type PatientOption = {
  id: number;
  name: string;
  phone: string;
};

export function ProjectPatientsTab({ projectId }: Props) {
  const queryClient = useQueryClient();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["project-patients", projectId],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>(
        "/studies/project-patients/",
        { params: { project: projectId } },
      );
      return r.data;
    },
  });

  const { data: patientCandidates, isLoading: isPatientsLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: async () => {
      const r = await apiClient.get<PatientOption[]>("/patients/");
      return r.data;
    },
    enabled: isAddOpen,
  });

  const selectOptions = useMemo(
    () =>
      (patientCandidates ?? []).map((p) => ({
        value: p.id,
        label: `${p.name}（${p.phone}）`,
      })),
    [patientCandidates],
  );

  const addMutation = useMutation({
    mutationFn: async (patientId: number) => {
      const r = await apiClient.post("/studies/project-patients/", {
        project: projectId,
        patient: patientId,
      });
      return r.data;
    },
    onSuccess: async () => {
      setIsAddOpen(false);
      setSelectedPatientId(null);
      await queryClient.invalidateQueries({ queryKey: ["project-patients", projectId] });
    },
    onError: (e: unknown) => {
      const detail =
        typeof e === "object" && e
          ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined;
      message.error(typeof detail === "string" && detail ? detail : "添加失败");
    },
  });

  return (
    <Card
      title="项目患者"
      extra={
        <Button
          type="primary"
          onClick={() => {
            setIsAddOpen(true);
          }}
        >
          添加患者
        </Button>
      }
    >
      <Modal
        title="添加患者到项目"
        open={isAddOpen}
        okText="添加"
        cancelText="取消"
        confirmLoading={addMutation.isPending}
        okButtonProps={{ disabled: !selectedPatientId }}
        onCancel={() => {
          setIsAddOpen(false);
          setSelectedPatientId(null);
        }}
        onOk={() => {
          if (!selectedPatientId) return;
          addMutation.mutate(selectedPatientId);
        }}
      >
        <Select
          style={{ width: "100%" }}
          placeholder="请选择患者"
          loading={isPatientsLoading}
          showSearch
          optionFilterProp="label"
          options={selectOptions}
          value={selectedPatientId ?? undefined}
          onChange={(v) => setSelectedPatientId(v)}
        />
      </Modal>
      <Table<ProjectPatientRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          { title: "姓名", dataIndex: "patient_name" },
          { title: "手机号", dataIndex: "patient_phone" },
          {
            title: "当前分组",
            dataIndex: "group_name",
            render: (v: string | null) => v ?? "—",
          },
          {
            title: "分组状态",
            dataIndex: "grouping_status",
            render: (v: string) => groupingLabel[v] ?? v,
          },
          {
            title: "操作",
            key: "actions",
            render: (_, row) => (
              <Space split="·">
                <Link to={`/crf?projectPatientId=${row.id}`}>CRF</Link>
                {row.visit_ids?.T0 ? (
                  <Link to={`/visits/${row.visit_ids.T0}`}>T0</Link>
                ) : null}
                {row.visit_ids?.T1 ? (
                  <Link to={`/visits/${row.visit_ids.T1}`}>T1</Link>
                ) : null}
                {row.visit_ids?.T2 ? (
                  <Link to={`/visits/${row.visit_ids.T2}`}>T2</Link>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
