import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Radio, Space, message } from "antd";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../../api/client";
import { isValidMainlandPhone } from "./doctorUtils";
import { backendErrorsToMessage, extractBackendFieldErrors, fieldErrorsToFormFields } from "./formErrorUtils";
import type { DoctorFormValues } from "./types";

export function DoctorCreatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form] = Form.useForm<DoctorFormValues>();

  const createMutation = useMutation({
    mutationFn: async (values: DoctorFormValues) => {
      await apiClient.post("/accounts/users/", {
        name: values.name.trim(),
        gender: values.gender,
        phone: values.phone.trim(),
      });
    },
    onSuccess: async () => {
      message.success("创建成功。默认密码为 888888，建议登录后立刻修改。");
      form.resetFields();
      await qc.invalidateQueries({ queryKey: ["doctors"] });
      navigate("/doctors");
    },
    onError: (err) => {
      const errors = extractBackendFieldErrors(err);
      const fields = fieldErrorsToFormFields(errors, ["phone"]);
      if (fields.length) {
        form.setFields(fields);
        return;
      }
      message.error(backendErrorsToMessage(errors) ?? "创建失败");
    },
  });

  return (
    <Card title="添加医生" extra={<Button onClick={() => navigate("/doctors")}>返回列表</Button>}>
      <Form<DoctorFormValues>
        form={form}
        layout="vertical"
        initialValues={{ gender: "unknown" }}
        onFinish={(v) => createMutation.mutate(v)}
        style={{ maxWidth: 560 }}
      >
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
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              创建
            </Button>
            <Button onClick={() => navigate("/doctors")}>取消</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
}
