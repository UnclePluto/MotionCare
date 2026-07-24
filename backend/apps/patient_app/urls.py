from django.urls import path

from .views import (
    PatientAppActionHistoryView,
    PatientAppBindView,
    PatientAppCurrentPrescriptionView,
    PatientAppHomeView,
    PatientAppMeView,
    PatientAppTrainingRecordView,
    PatientAppTrainingVideoSegmentView,
    PatientAppTrainingVideoSessionCollectionView,
    PatientAppTrainingVideoSessionDetailView,
    PatientAppTrainingVideoSessionFinishView,
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
        "training-video-sessions/",
        PatientAppTrainingVideoSessionCollectionView.as_view(),
        name="patient-app-training-video-session-create",
    ),
    path(
        "training-video-sessions/<int:video_id>/segments/",
        PatientAppTrainingVideoSegmentView.as_view(),
        name="patient-app-training-video-segment-upload",
    ),
    path(
        "training-video-sessions/<int:video_id>/",
        PatientAppTrainingVideoSessionDetailView.as_view(),
        name="patient-app-training-video-session-detail",
    ),
    path(
        "training-video-sessions/<int:video_id>/finish/",
        PatientAppTrainingVideoSessionFinishView.as_view(),
        name="patient-app-training-video-session-finish",
    ),
    path(
        "actions/<int:prescription_action_id>/history/",
        PatientAppActionHistoryView.as_view(),
        name="patient-app-action-history",
    ),
]
