import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";

function Placeholder({ title }: { title: string }) {
  return <h1>{title}页面</h1>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/patients" element={<Placeholder title="患者档案" />} />
          <Route path="/projects" element={<Placeholder title="研究项目" />} />
          <Route path="/training" element={<Placeholder title="训练记录" />} />
          <Route path="/crf" element={<Placeholder title="CRF 报告" />} />
          <Route path="*" element={<Navigate to="/patients" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

