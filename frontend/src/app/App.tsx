import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";
import { PatientListPage } from "../pages/patients/PatientListPage";
import { ProjectDetailPage } from "../pages/projects/ProjectDetailPage";
import { ProjectListPage } from "../pages/projects/ProjectListPage";
import { VisitFormPage } from "../pages/visits/VisitFormPage";
import { TrainingEntryPage } from "../pages/training/TrainingEntryPage";
import { DailyHealthPage } from "../pages/health/DailyHealthPage";
import { CrfPreviewPage } from "../pages/crf/CrfPreviewPage";

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
          <Route path="/visits/:visitId" element={<VisitFormPage />} />
          <Route path="/training" element={<TrainingEntryPage />} />
          <Route path="/health" element={<DailyHealthPage />} />
          <Route path="/crf" element={<CrfPreviewPage />} />
          <Route path="*" element={<Navigate to="/patients" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

