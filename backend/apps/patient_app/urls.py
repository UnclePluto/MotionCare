from django.urls import path

from .views import (
    PatientAppActionHistoryView,
    PatientAppBindView,
    PatientAppCurrentPrescriptionView,
    PatientAppDailyHealthTodayView,
    PatientAppHomeView,
    PatientAppMeView,
    PatientAppTrainingRecordView,
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
