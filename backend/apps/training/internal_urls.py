from django.urls import path

from .internal_views import (
    MotionAnalysisClaimView,
    MotionAnalysisCompleteView,
    MotionAnalysisFailView,
    MotionAnalysisHeartbeatView,
)


urlpatterns = [
    path("jobs/claim/", MotionAnalysisClaimView.as_view(), name="motion-analysis-internal-claim"),
    path(
        "jobs/<int:job_id>/heartbeat/",
        MotionAnalysisHeartbeatView.as_view(),
        name="motion-analysis-internal-heartbeat",
    ),
    path(
        "jobs/<int:job_id>/complete/",
        MotionAnalysisCompleteView.as_view(),
        name="motion-analysis-internal-complete",
    ),
    path(
        "jobs/<int:job_id>/fail/",
        MotionAnalysisFailView.as_view(),
        name="motion-analysis-internal-fail",
    ),
]
