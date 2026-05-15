import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Radio, Space, message } from "antd";
import { isAxiosError } from "axios";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { isValidMainlandPhone } from "./doctorUtils";
import { backendErrorsToMessage, extractBackendFieldErrors, fieldErrorsToFormFields } from "./formErrorUtils";
import type { Doctor, DoctorFormValues } from "./types";

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  if ("detail" in data && typeof (data as { detail?: unknown }).detail === "string") {
    return (data as { detail: string }).detail;
  }
  return Object.entries(data as Record<string, unknown>)
    .map(([key, value]) => (Array.isArray(value) ? `${key}: ${value.map(String).join(", ")}` : `${key}: ${String(value)}`))
    .join("；");
}

export function DoctorEditPage() {
  const { doctorId } = useParams();
  const id = Number(doctorId);
  const doctorQueryKey = ["doctor", String(id)];
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form] = Form.useForm<DoctorFormValues>();

  const {
    data: doctor,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: doctorQueryKey,
    queryFn: async () => {
      const r = await apiClient.get<Doctor>(`/accounts/users/${id}/`);
      return r.data;
    },
    enabled: Number.isSafeInteger(id) && id > 0,
  });

  useEffect(() => {
    if (!doctor) return;
    form.setFieldsValue({ name: doctor.name, gender: doctor.gender, phone: doctor.phone });
  }, [doctor, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: DoctorFormValues) => {
      await apiClient.patch(`/accounts/users/${id}/`, {
        name: values.name.trim(),
        gender: values.gender,
        phone: values.phone.trim(),
      });
    },
    onSuccess: async () => {
      message.success("医生资料已保存");
      await qc.invalidateQueries({ queryKey: ["doctors"] });
      await qc.invalidateQueries({ queryKey: doctorQueryKey });
      navigate("/doctors");
    },
    onError: (err) => {
      const errors = extractBackendFieldErrors(err);
      const fields = fieldErrorsToFormFields(errors, ["phone"]);
      if (fields.length) {
        form.setFields(fields);
        return;
      }
      message.error(backendErrorsToMessage(errors) || "保存失败");
    },
  });

  if (!Number.isSafeInteger(id) || id <= 0) return <Alert type="error" message="无效的医生 ID" />;
  if (isError) return <Alert type="error" message={backendDetail(error) || "医生不存在或无权限访问"} />;

  return (
    <Card
      loading={isLoading}
      title={doctor ? `编辑：${doctor.name}` : "编辑医生"}
      extra={<Button onClick={() => navigate("/doctors")}>返回列表</Button>}
    >
      {doctor && (
        <Form<DoctorFormValues> form={form} layout="vertical" onFinish={(v) => saveMutation.mutate(v)} style={{ maxWidth: 560 }}>
          <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="性别" name="gender" rules={[{ required: true }]}>
            <Radio.Group
              options={[
                { value: "male", label: "男" },
                { value: "female", label: "女" },
                { value: "unknown", label: "未知" },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="手机号"
            name="phone"
            rules={[
              { required: true, message: "请输入手机号" },
              {
                validator(_, value) {
                  if (!value || isValidMainlandPhone(value)) return Promise.resolve();
                  return Promise.reject(new Error("请输入 11 位有效手机号"));
                },
              },
            ]}
          >
            <Input />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
                保存
              </Button>
              <Button onClick={() => navigate("/doctors")}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      )}
    </Card>
  );
}
