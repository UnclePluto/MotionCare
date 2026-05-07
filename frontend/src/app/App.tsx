import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";
import { PatientListPage } from "../pages/patients/PatientListPage";
import { ProjectDetailPage } from "../pages/projects/ProjectDetailPage";
import { ProjectListPage } from "../pages/projects/ProjectListPage";

function Placeholder({ title }: { title: string }) {
  return <h1>{title}页面</h1>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/patients" element={<PatientListPage />} />
          <Route path="/projects" element={<ProjectListPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/training" element={<Placeholder title="训练记录" />} />
          <Route path="/crf" element={<Placeholder title="CRF 报告" />} />
          <Route path="*" element={<Navigate to="/patients" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

