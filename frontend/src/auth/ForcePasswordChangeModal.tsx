import { Button, Form, Input, Modal, Space, Typography, message } from "antd";
import { useState } from "react";

import { apiClient } from "../api/client";
import { backendErrorsToMessage, extractBackendFieldErrors, fieldErrorsToFormFields } from "../pages/doctors/formErrorUtils";

type PasswordFormValues = {
  old_password: string;
  new_password: string;
  confirm_password: string;
};

export function ForcePasswordChangeModal({
  open,
  onChanged,
  onLogout,
}: {
  open: boolean;
  onChanged: () => void;
  onLogout: () => void;
}) {
  const [form] = Form.useForm<PasswordFormValues>();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: PasswordFormValues) => {
    setSubmitting(true);
    try {
      await apiClient.post("/accounts/users/me/change-password/", values);
      message.success("密码已修改");
      form.resetFields();
      onChanged();
    } catch (err) {
      const errors = extractBackendFieldErrors(err);
      const fields = fieldErrorsToFormFields(errors, ["old_password", "new_password", "confirm_password"]);
      if (fields.length) {
        form.setFields(fields);
      } else {
        message.error(backendErrorsToMessage(errors) ?? "修改密码失败");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="请先修改默认密码"
      open={open}
      footer={null}
      closable={false}
      maskClosable={false}
      keyboard={false}
      destroyOnHidden
      getContainer={false}
    >
      <Typography.Paragraph type="secondary">
        当前账号仍在使用系统默认密码。修改密码后才可以继续使用系统。
      </Typography.Paragraph>
      <Form<PasswordFormValues> form={form} layout="vertical" onFinish={onFinish}>
        <Form.Item label="原密码" name="old_password" rules={[{ required: true, message: "请输入原密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          label="新密码"
          name="new_password"
          rules={[{ required: true, message: "请输入新密码" }]}
        >
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
            <Button type="primary" htmlType="submit" loading={submitting}>
              修改密码
            </Button>
            <Button onClick={onLogout}>退出登录</Button>
          </Space>
        </Form.Item>
      </Form>
    </Modal>
  );
}
