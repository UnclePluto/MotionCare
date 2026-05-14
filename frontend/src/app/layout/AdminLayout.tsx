import { Button, Layout, Menu, Space, Typography } from "antd";
import {
  FileTextOutlined,
  FormOutlined,
  HeartOutlined,
  MedicineBoxOutlined,
  ProjectOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";

const { Header, Sider, Content } = Layout;

export function AdminLayout() {
  const navigate = useNavigate();
  const { me, logout } = useAuth();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={220}>
        <div style={{ color: "#fff", padding: 16, fontWeight: 600 }}>
          MotionCare
        </div>
        <Menu
          theme="dark"
          mode="inline"
          onClick={(item) => navigate(item.key)}
          items={[
            { key: "/patients", icon: <TeamOutlined />, label: "患者档案" },
            { key: "/research-entry", icon: <FormOutlined />, label: "研究录入" },
            { key: "/prescriptions", icon: <MedicineBoxOutlined />, label: "处方管理" },
            { key: "/projects", icon: <ProjectOutlined />, label: "研究项目" },
            { key: "/training", icon: <HeartOutlined />, label: "训练记录" },
            { key: "/crf", icon: <FileTextOutlined />, label: "CRF 报告" },
          ]}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            paddingInline: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>医院康复研究后台</span>
          <Space>
            <Typography.Text type="secondary">
              {me?.name}（{me?.phone}）
            </Typography.Text>
            <Button onClick={() => void logout()}>退出</Button>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
