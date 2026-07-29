import { Alert } from "antd";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";

import { AuthProvider } from "../auth/AuthContext";
import { RequireAuth } from "../auth/RequireAuth";
import { AccountPage } from "../pages/account/AccountPage";
import { LoginPage } from "../pages/auth/LoginPage";
import { AdminLayout } from "./layout/AdminLayout";
import { PatientCrfBaselinePage } from "../pages/patients/PatientCrfBaselinePage";
import { PatientListPage } from "../pages/patients/PatientListPage";
import { PatientDetailPage } from "../pages/patients/PatientDetailPage";
import { PatientEditPage } from "../pages/patients/PatientEditPage";
import { PrescriptionEntryPage } from "../pages/prescriptions/PrescriptionEntryPage";
import { PrescriptionPanel } from "../pages/prescriptions/PrescriptionPanel";
import { ProjectDetailPage } from "../pages/projects/ProjectDetailPage";
import { ProjectListPage } from "../pages/projects/ProjectListPage";
import { ProjectPatientResearchEntryPage } from "../pages/research-entry/ProjectPatientResearchEntryPage";
import { ResearchEntryPage } from "../pages/research-entry/ResearchEntryPage";
import { VisitFormPage } from "../pages/visits/VisitFormPage";
import { TrainingEntryPage } from "../pages/training/TrainingEntryPage";
import { TrainingTrackingDetailPage } from "../pages/training-tracking/TrainingTrackingDetailPage";
import { TrainingTrackingPage } from "../pages/training-tracking/TrainingTrackingPage";
import { CrfPreviewPage } from "../pages/crf/CrfPreviewPage";
import { DoctorCreatePage } from "../pages/doctors/DoctorCreatePage";
import { DoctorEditPage } from "../pages/doctors/DoctorEditPage";
import { DoctorListPage } from "../pages/doctors/DoctorListPage";
import { DeviceInventoryPage } from "../pages/wearables/DeviceInventoryPage";

function PrescriptionRouteWrapper() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  const id = Number(projectPatientId);
  if (!Number.isSafeInteger(id) || id <= 0) {
    return <Alert type="error" message="无效的项目患者 ID" />;
  }
  return <PrescriptionPanel projectPatientId={id} />;
}

function LegacyPrescriptionRouteRedirect() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  return <Navigate to={`/prescriptions/project-patients/${projectPatientId ?? ""}`} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AdminLayout />}>
              <Route path="/patients" element={<PatientListPage />} />
              <Route path="/patients/:patientId/crf-baseline" element={<PatientCrfBaselinePage />} />
              <Route path="/patients/:patientId/edit" element={<PatientEditPage />} />
              <Route path="/patients/:patientId" element={<PatientDetailPage />} />
              <Route path="/projects" element={<ProjectListPage />} />
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="/research-entry" element={<ResearchEntryPage />} />
              <Route path="/research-entry/project-patients/:projectPatientId" element={<ProjectPatientResearchEntryPage />} />
              <Route path="/prescriptions" element={<PrescriptionEntryPage />} />
              <Route path="/prescriptions/project-patients/:projectPatientId" element={<PrescriptionRouteWrapper />} />
              <Route
                path="/research-entry/project-patients/:projectPatientId/prescriptions"
                element={<LegacyPrescriptionRouteRedirect />}
              />
              <Route path="/doctors" element={<DoctorListPage />} />
              <Route path="/doctors/new" element={<DoctorCreatePage />} />
              <Route path="/doctors/:doctorId/edit" element={<DoctorEditPage />} />
              <Route path="/account" element={<AccountPage />} />
              <Route path="/visits/:visitId" element={<VisitFormPage />} />
              <Route path="/training" element={<TrainingEntryPage />} />
              <Route path="/training-tracking" element={<TrainingTrackingPage />} />
              <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
              <Route path="/wearable-devices" element={<DeviceInventoryPage />} />
              <Route path="/crf" element={<CrfPreviewPage />} />
              <Route path="*" element={<Navigate to="/patients" replace />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
