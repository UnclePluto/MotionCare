import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../auth/AuthContext";
import { RequireAuth } from "../auth/RequireAuth";
import { LoginPage } from "../pages/auth/LoginPage";
import { AdminLayout } from "./layout/AdminLayout";
import { PatientListPage } from "../pages/patients/PatientListPage";
import { PatientDetailPage } from "../pages/patients/PatientDetailPage";
import { ProjectDetailPage } from "../pages/projects/ProjectDetailPage";
import { ProjectListPage } from "../pages/projects/ProjectListPage";
import { VisitFormPage } from "../pages/visits/VisitFormPage";
import { TrainingEntryPage } from "../pages/training/TrainingEntryPage";
import { DailyHealthPage } from "../pages/health/DailyHealthPage";
import { CrfPreviewPage } from "../pages/crf/CrfPreviewPage";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AdminLayout />}>
              <Route path="/patients" element={<PatientListPage />} />
              <Route path="/patients/:patientId" element={<PatientDetailPage />} />
              <Route path="/projects" element={<ProjectListPage />} />
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="/visits/:visitId" element={<VisitFormPage />} />
              <Route path="/training" element={<TrainingEntryPage />} />
              <Route path="/health" element={<DailyHealthPage />} />
              <Route path="/crf" element={<CrfPreviewPage />} />
              <Route path="*" element={<Navigate to="/patients" replace />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
