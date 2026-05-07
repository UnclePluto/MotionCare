import { Layout, Menu } from "antd";
import {
  FileTextOutlined,
  HeartOutlined,
  ProjectOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Outlet, useNavigate } from "react-router-dom";

const { Header, Sider, Content } = Layout;

export function AdminLayout() {
  const navigate = useNavigate();
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
            { key: "/projects", icon: <ProjectOutlined />, label: "研究项目" },
            { key: "/training", icon: <HeartOutlined />, label: "训练记录" },
            { key: "/crf", icon: <FileTextOutlined />, label: "CRF 报告" },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", paddingInline: 24 }}>
          医院康复研究后台
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

