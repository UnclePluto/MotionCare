from django.urls import path

from .views import (
    PatientAppActionHistoryView,
    PatientAppBindView,
    PatientAppCurrentPrescriptionView,
    DemoMotionVideoManifestView,
    PatientAppHomeView,
    PatientAppMeView,
    PatientAppTrainingRecordView,
    PatientAppTrainingVideoFinalizeView,
    PatientAppTrainingVideoSegmentView,
    PatientAppTrainingVideoSessionView,
    PatientAppTrainingVideoStatusView,
)

urlpatterns = [
    path("bind/", PatientAppBindView.as_view(), name="patient-app-bind"),
    path(
        "demo-motion-videos/",
        DemoMotionVideoManifestView.as_view(),
        name="patient-app-demo-motion-videos",
    ),
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
        "training-video-sessions/",
        PatientAppTrainingVideoSessionView.as_view(),
        name="patient-app-training-video-session",
    ),
    path(
        "training-video-sessions/<int:video_id>/segments/<int:index>/",
        PatientAppTrainingVideoSegmentView.as_view(),
        name="patient-app-training-video-segment",
    ),
    path(
        "training-video-sessions/<int:video_id>/finalize/",
        PatientAppTrainingVideoFinalizeView.as_view(),
        name="patient-app-training-video-finalize",
    ),
    path(
        "training-video-sessions/<int:video_id>/status/",
        PatientAppTrainingVideoStatusView.as_view(),
        name="patient-app-training-video-status",
    ),
    path(
        "actions/<int:prescription_action_id>/history/",
        PatientAppActionHistoryView.as_view(),
        name="patient-app-action-history",
    ),
]
