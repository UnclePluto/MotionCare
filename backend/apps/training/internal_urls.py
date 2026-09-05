from django.urls import path

from .internal_views import MotionAnalysisClaimView, MotionAnalysisHeartbeatView


urlpatterns = [
    path("jobs/claim/", MotionAnalysisClaimView.as_view(), name="motion-analysis-internal-claim"),
    path(
        "jobs/<int:job_id>/heartbeat/",
        MotionAnalysisHeartbeatView.as_view(),
        name="motion-analysis-internal-heartbeat",
    ),
]
