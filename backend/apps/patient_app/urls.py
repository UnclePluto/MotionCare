from django.urls import path

from .views import (
    PatientAppActionHistoryView,
    PatientAppBindView,
    PatientAppCurrentPrescriptionView,
    PatientAppDailyHealthTodayView,
    PatientAppHomeView,
    PatientAppMeView,
    PatientAppTrainingRecordView,
    PatientAppTrainingVideoCompleteView,
    PatientAppTrainingVideoUploadIntentView,
)

urlpatterns = [
    path("bind/", PatientAppBindView.as_view(), name="patient-app-bind"),
    path("me/", PatientAppMeView.as_view(), name="patient-app-me"),
    path("home/", PatientAppHomeView.as_view(), name="patient-app-home"),
    path(
        "current-prescription/",
        PatientAppCurrentPrescriptionView.as_view(),
        name="patient-app-current-prescription",
    ),
    path(
        "training-records/",
        PatientAppTrainingRecordView.as_view(),
        name="patient-app-training-records",
    ),
    path(
        "training-videos/upload-intent/",
        PatientAppTrainingVideoUploadIntentView.as_view(),
        name="patient-app-training-video-upload-intent",
    ),
    path(
        "training-videos/<int:video_id>/complete/",
        PatientAppTrainingVideoCompleteView.as_view(),
        name="patient-app-training-video-complete",
    ),
    path(
        "actions/<int:prescription_action_id>/history/",
        PatientAppActionHistoryView.as_view(),
        name="patient-app-action-history",
    ),
    path(
        "daily-health/today/",
        PatientAppDailyHealthTodayView.as_view(),
        name="patient-app-daily-health-today",
    ),
]
