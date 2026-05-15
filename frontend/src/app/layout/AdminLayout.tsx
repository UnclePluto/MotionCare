import { Button, Layout, Menu, Space } from "antd";
import {
  FileTextOutlined,
  FormOutlined,
  HeartOutlined,
  MedicineBoxOutlined,
  ProjectOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { ForcePasswordChangeModal } from "../../auth/ForcePasswordChangeModal";
import { useAuth } from "../../auth/AuthContext";
import { maskPhoneForList } from "../../pages/patients/phoneMask";

const { Header, Sider, Content } = Layout;

export function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { me, logout, refetchSession } = useAuth();
  const selectedKey = `/${location.pathname.split("/").filter(Boolean)[0] ?? "patients"}`;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={220}>
        <div style={{ color: "#fff", padding: 16, fontWeight: 600 }}>
          MotionCare
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          onClick={(item) => navigate(item.key)}
          items={[
            { key: "/patients", icon: <TeamOutlined />, label: "患者档案" },
            { key: "/research-entry", icon: <FormOutlined />, label: "研究录入" },
            { key: "/prescriptions", icon: <MedicineBoxOutlined />, label: "处方管理" },
            { key: "/projects", icon: <ProjectOutlined />, label: "研究项目" },
            { key: "/doctors", icon: <UserOutlined />, label: "医生管理" },
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
            <Button type="link" onClick={() => navigate("/account")}>
              {me?.name}（{maskPhoneForList(me?.phone ?? "")}）
            </Button>
            <Button onClick={() => void logout()}>退出</Button>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
          <ForcePasswordChangeModal
            open={me?.must_change_password === true}
            onChanged={() => void refetchSession()}
            onLogout={() => void logout()}
          />
        </Content>
      </Layout>
    </Layout>
  );
}
