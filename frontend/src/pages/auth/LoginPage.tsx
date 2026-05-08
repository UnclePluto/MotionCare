import { Button, Card, Form, Input, Spin, Typography, message } from "antd";
import axios from "axios";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";

type LoginFormValues = {
  phone: string;
  password: string;
};

export function LoginPage() {
  const { me, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);

  const from =
    (location.state as { from?: string } | null)?.from &&
    (location.state as { from?: string }).from !== "/login"
      ? (location.state as { from: string }).from
      : "/patients";

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (me) {
    return <Navigate to={from} replace />;
  }

  const onFinish = async (values: LoginFormValues) => {
    setSubmitting(true);
    try {
      await login(values.phone.trim(), values.password);
      message.success("登录成功");
      navigate(from, { replace: true });
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.data?.message) {
        message.error(String(e.response.data.message));
        return;
      }
      message.error("登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f0f2f5",
        padding: 24,
      }}
    >
      <Card style={{ width: 400 }} title="MotionCare 管理后台">
        <Typography.Paragraph type="secondary" style={{ marginBottom: 24 }}>
          使用手机号与密码登录（本地演示账号见「开发说明」）。
        </Typography.Paragraph>
        <Form<LoginFormValues> layout="vertical" onFinish={onFinish}>
          <Form.Item
            label="手机号"
            name="phone"
            rules={[{ required: true, message: "请输入手机号" }]}
          >
            <Input placeholder="手机号" autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
