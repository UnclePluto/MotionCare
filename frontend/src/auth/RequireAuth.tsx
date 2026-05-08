import { Alert, Button, Spin } from "antd";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";

export function RequireAuth() {
  const { me, loading, error, refetchSession } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: 480, margin: "48px auto", padding: 24 }}>
        <Alert
          type="error"
          showIcon
          message="无法验证登录状态"
          description={String((error as Error)?.message ?? error)}
          action={
            <Button size="small" type="primary" onClick={() => refetchSession()}>
              重试
            </Button>
          }
        />
      </div>
    );
  }

  if (me === null) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
