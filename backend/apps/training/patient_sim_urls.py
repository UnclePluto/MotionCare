from django.urls import path

from .patient_sim_views import PatientSimCurrentPrescriptionView, PatientSimTrainingRecordView

urlpatterns = [
    path(
        "project-patients/<int:project_patient_id>/current-prescription/",
        PatientSimCurrentPrescriptionView.as_view(),
        name="patient-sim-current-prescription",
    ),
    path(
        "project-patients/<int:project_patient_id>/training-records/",
        PatientSimTrainingRecordView.as_view(),
        name="patient-sim-training-records",
    ),
]
