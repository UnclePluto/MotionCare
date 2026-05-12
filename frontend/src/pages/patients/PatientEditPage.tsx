import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Form, Input, Select, Space, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { isAxiosError } from "axios";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { ageFromBirthDate } from "./ageFromBirthDate";

type Patient = {
  id: number;
  name: string;
  phone: string;
  gender?: string | null;
  birth_date?: string | null;
  age?: number | null;
  symptom_note?: string | null;
  is_active?: boolean;
};

type PatientFormValues = {
  name: string;
  gender: "male" | "female" | "unknown";
  birth_date?: Dayjs | null;
  phone: string;
  symptom_note?: string;
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

export function PatientEditPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { patientId } = useParams();
  const id = Number(patientId);
  const [form] = Form.useForm<PatientFormValues>();

  const { data: patient, isLoading, isError, error } = useQuery({
    queryKey: ["patient", patientId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<Patient>(`/patients/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  useEffect(() => {
    if (!patient) return;
    form.setFieldsValue({
      name: patient.name,
      gender: (patient.gender as PatientFormValues["gender"]) ?? "unknown",
      birth_date: patient.birth_date ? dayjs(patient.birth_date) : undefined,
      phone: patient.phone,
      symptom_note: patient.symptom_note ?? "",
    });
  }, [patient, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: PatientFormValues) => {
      const bd = values.birth_date;
      await apiClient.patch(`/patients/${id}/`, {
        name: values.name.trim(),
        gender: values.gender,
        birth_date: bd ? bd.format("YYYY-MM-DD") : null,
        age: bd ? ageFromBirthDate(bd) : null,
        phone: values.phone.trim(),
        symptom_note: (values.symptom_note ?? "").trim(),
        is_active: patient?.is_active !== false,
      });
    },
    onSuccess: async () => {
      message.success("已保存");
      await qc.invalidateQueries({ queryKey: ["patient", String(id)] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
      navigate(`/patients/${id}`);
    },
    onError: (err) => message.error(backendDetail(err) ?? "保存失败"),
  });

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
      title={patient ? `编辑：${patient.name}` : "编辑患者档案"}
      extra={
        <Button onClick={() => navigate(`/patients/${id}`)} disabled={!Number.isFinite(id)}>
          返回详情
        </Button>
      }
    >
      {patient && (
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
          <Form.Item label="年龄" shouldUpdate={(prev, cur) => prev.birth_date !== cur.birth_date}>
            {() => {
              const bd = form.getFieldValue("birth_date") as Dayjs | undefined;
              if (!bd) {
                return <Input readOnly placeholder="请先选择出生日期" />;
              }
              return <Input readOnly value={String(ageFromBirthDate(bd))} />;
            }}
          </Form.Item>
          <Form.Item label="手机号" name="phone" rules={[{ required: true, message: "请输入手机号" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="备注" name="symptom_note">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
                保存
              </Button>
              <Button onClick={() => navigate(`/patients/${id}`)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      )}
    </Card>
  );
}
