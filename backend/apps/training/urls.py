from django.urls import path
from rest_framework.routers import DefaultRouter

from .tracking_views import TrackingPatientDetailView, TrackingPatientListView
from .video_views import (
    TrainingVideoAnalysisJobView,
    TrainingVideoDownloadUrlView,
    TrainingVideoLatestAnalysisJobView,
    TrainingVideoWearableWindowView,
)
from .views import TrainingRecordViewSet

router = DefaultRouter()
router.register("", TrainingRecordViewSet, basename="training-record")
urlpatterns = [
    path("tracking/patients/", TrackingPatientListView.as_view()),
    path("tracking/patients/<int:patient_id>/", TrackingPatientDetailView.as_view()),
    path(
        "videos/<int:video_id>/download-url/",
        TrainingVideoDownloadUrlView.as_view(),
    ),
    path(
        "videos/<int:video_id>/wearable-window/",
        TrainingVideoWearableWindowView.as_view(),
    ),
    path(
        "videos/<int:video_id>/analysis-jobs/",
        TrainingVideoAnalysisJobView.as_view(),
    ),
    path(
        "videos/<int:video_id>/analysis-jobs/latest/",
        TrainingVideoLatestAnalysisJobView.as_view(),
    ),
    *router.urls,
]
