import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Card, Divider, Form, Input, Radio, Space, message } from "antd";
import { useEffect } from "react";

import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { isValidMainlandPhone } from "../doctors/doctorUtils";
import { backendErrorsToMessage, extractBackendFieldErrors, fieldErrorsToFormFields } from "../doctors/formErrorUtils";
import type { DoctorFormValues } from "../doctors/types";

type PasswordValues = {
  old_password: string;
  new_password: string;
  confirm_password: string;
};

export function AccountPage() {
  const { me, refetchSession } = useAuth();
  const [profileForm] = Form.useForm<DoctorFormValues>();
  const [passwordForm] = Form.useForm<PasswordValues>();

  useEffect(() => {
    if (!me) return;
    profileForm.setFieldsValue({ name: me.name, gender: me.gender, phone: me.phone });
  }, [me, profileForm]);

  const profileMutation = useMutation({
    mutationFn: async (values: DoctorFormValues) => {
      if (!me) return;
      await apiClient.patch(`/accounts/users/${me.id}/`, {
        name: values.name.trim(),
        gender: values.gender,
        phone: values.phone.trim(),
      });
    },
    onSuccess: async () => {
      message.success("账号资料已保存");
      await refetchSession();
    },
    onError: (err) => {
      const errors = extractBackendFieldErrors(err);
      const fields = fieldErrorsToFormFields(errors, ["phone"]);
      if (fields.length) {
        profileForm.setFields(fields);
        return;
      }
      message.error(backendErrorsToMessage(errors) || "保存失败");
    },
  });

  const passwordMutation = useMutation({
    mutationFn: async (values: PasswordValues) => {
      await apiClient.post("/accounts/users/me/change-password/", values);
    },
    onSuccess: async () => {
      message.success("密码已修改");
      passwordForm.resetFields();
      await refetchSession();
    },
    onError: (err) => {
      const errors = extractBackendFieldErrors(err);
      const fields = fieldErrorsToFormFields(errors, ["old_password", "new_password", "confirm_password"]);
      if (fields.length) {
        passwordForm.setFields(fields);
        return;
      }
      message.error(backendErrorsToMessage(errors) || "修改密码失败");
    },
  });

  if (!me) return <Alert type="error" message="无法读取当前账号" />;

  return (
    <Card title="我的账号">
      <Form<DoctorFormValues> form={profileForm} layout="vertical" onFinish={(v) => profileMutation.mutate(v)} style={{ maxWidth: 560 }}>
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
          <Button type="primary" htmlType="submit" loading={profileMutation.isPending}>
            保存资料
          </Button>
        </Form.Item>
      </Form>

      <Divider orientation="left">修改密码</Divider>
      <Form<PasswordValues> form={passwordForm} layout="vertical" onFinish={(v) => passwordMutation.mutate(v)} style={{ maxWidth: 560 }}>
        <Form.Item label="原密码" name="old_password" rules={[{ required: true, message: "请输入原密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item label="新密码" name="new_password" rules={[{ required: true, message: "请输入新密码" }]}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          label="确认新密码"
          name="confirm_password"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("new_password") === value) return Promise.resolve();
                return Promise.reject(new Error("两次输入的新密码不一致"));
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={passwordMutation.isPending}>
              修改密码
            </Button>
            <Button onClick={() => passwordForm.resetFields()}>清空</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
}
