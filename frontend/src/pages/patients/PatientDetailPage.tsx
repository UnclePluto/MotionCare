import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { isAxiosError } from "axios";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { EnrollProjectsModal } from "./components/EnrollProjectsModal";

type Patient = {
  id: number;
  name: string;
  phone: string;
  gender?: string | null;
  birth_date?: string | null;
  age?: number | null;
  primary_doctor?: number | null;
  symptom_note?: string | null;
  is_active?: boolean;
};

type StudyProject = { id: number; name: string };

type ProjectPatientRow = {
  id: number;
  project: number;
  patient_name: string;
  group_name: string | null;
  grouping_status: string;
};

type PatientFormValues = {
  name: string;
  gender: "male" | "female" | "unknown";
  birth_date?: Dayjs | null;
  age?: number | null;
  phone: string;
  symptom_note?: string;
  is_active: boolean;
};

const groupingStatusLabel: Record<string, string> = {
  pending: "待确认",
  confirmed: "已确认",
};

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  if ("detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "detail" in (d as object)) {
      const inner = (d as { detail?: unknown }).detail;
      if (typeof inner === "string") return inner;
    }
  }
  return null;
}

export function PatientDetailPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { patientId } = useParams();
  const id = Number(patientId);
  const [form] = Form.useForm<PatientFormValues>();
  const [enrollOpen, setEnrollOpen] = useState(false);

  const { data: patient, isLoading, isError, error } = useQuery({
    queryKey: ["patient", patientId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<Patient>(`/patients/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const { data: projectPatients = [], isLoading: ppLoading } = useQuery({
    queryKey: ["project-patients", "patient", id],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>(`/studies/project-patients/?patient=${id}`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const projectNameById = useMemo(
    () => Object.fromEntries(projects.map((p) => [p.id, p.name])) as Record<number, string>,
    [projects],
  );

  useEffect(() => {
    if (!patient) return;
    form.setFieldsValue({
      name: patient.name,
      gender: (patient.gender as PatientFormValues["gender"]) ?? "unknown",
      birth_date: patient.birth_date ? dayjs(patient.birth_date) : undefined,
      age: patient.age ?? undefined,
      phone: patient.phone,
      symptom_note: patient.symptom_note ?? "",
      is_active: patient.is_active !== false,
    });
  }, [patient, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: PatientFormValues) => {
      await apiClient.patch(`/patients/${id}/`, {
        name: values.name.trim(),
        gender: values.gender,
        birth_date: values.birth_date ? values.birth_date.format("YYYY-MM-DD") : null,
        age: values.age ?? null,
        phone: values.phone.trim(),
        symptom_note: (values.symptom_note ?? "").trim(),
        is_active: values.is_active,
      });
    },
    onSuccess: async () => {
      message.success("已保存");
      await qc.invalidateQueries({ queryKey: ["patient", String(id)] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err) => message.error(backendDetail(err) ?? "保存失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      await apiClient.delete(`/patients/${id}/`);
    },
    onSuccess: async () => {
      message.success("患者档案已删除");
      await qc.invalidateQueries({ queryKey: ["patients"] });
      navigate("/patients");
    },
    onError: (err) => message.error(backendDetail(err) ?? "删除失败"),
  });

  const confirmDelete = () => {
    Modal.confirm({
      title: "确认删除患者档案？",
      content: "若患者仍关联研究项目，系统将拒绝删除，可改用下方「停用档案」。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: () => deleteMutation.mutateAsync(),
    });
  };

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的患者 ID" />;
  }

  if (isError) {
    const d = backendDetail(error);
    return <Alert type="error" message={d ?? "患者不存在或无权限访问"} />;
  }

  return (
    <Card
      loading={isLoading}
      title={patient ? patient.name : "患者详情"}
      extra={
        <Space>
          <Button onClick={() => setEnrollOpen(true)}>加入研究项目</Button>
          <Button danger onClick={confirmDelete} loading={deleteMutation.isPending}>
            删除档案
          </Button>
        </Space>
      }
    >
      {patient && (
        <>
          <Form<PatientFormValues>
            form={form}
            layout="vertical"
            onFinish={(v) => saveMutation.mutate(v)}
            style={{ maxWidth: 560 }}
          >
            <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
              <Input />
            </Form.Item>
            <Form.Item label="性别" name="gender" rules={[{ required: true }]}>
              <Select
                options={[
                  { value: "male", label: "男" },
                  { value: "female", label: "女" },
                  { value: "unknown", label: "未知" },
                ]}
              />
            </Form.Item>
            <Form.Item label="出生日期" name="birth_date">
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="年龄" name="age">
              <InputNumber min={0} max={130} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="手机号" name="phone" rules={[{ required: true, message: "请输入手机号" }]}>
              <Input />
            </Form.Item>
            <Form.Item label="备注" name="symptom_note">
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item label="档案启用" name="is_active" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
                保存修改
              </Button>
            </Form.Item>
          </Form>

          <Divider orientation="left">研究项目参与</Divider>
          <Table<ProjectPatientRow>
            rowKey="id"
            loading={ppLoading}
            dataSource={projectPatients}
            pagination={false}
            columns={[
              {
                title: "项目名称",
                key: "projectName",
                render: (_: unknown, row) => projectNameById[row.project] ?? `项目 #${row.project}`,
              },
              {
                title: "分组",
                dataIndex: "group_name",
                render: (v: string | null) => v ?? "—",
              },
              {
                title: "分组状态",
                dataIndex: "grouping_status",
                render: (v: string) => groupingStatusLabel[v] ?? v,
              },
              {
                title: "操作",
                key: "crf",
                render: (_: unknown, row) => (
                  <Link to={`/crf?projectPatientId=${row.id}`}>打开 CRF</Link>
                ),
              },
            ]}
          />

          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="随访与访视"
            description="后续版本将在此关联访视计划与 CRF 随访入口；本期请从上方「打开 CRF」进入录入。"
          />

          <EnrollProjectsModal open={enrollOpen} onClose={() => setEnrollOpen(false)} patientId={id} />
        </>
      )}
    </Card>
  );
}
