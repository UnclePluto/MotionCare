from django.urls import path
from rest_framework.routers import DefaultRouter

from .tracking_views import TrackingPatientDetailView, TrackingPatientListView
from .views import TrainingRecordViewSet

router = DefaultRouter()
router.register("", TrainingRecordViewSet, basename="training-record")
urlpatterns = [
    path("tracking/patients/", TrackingPatientListView.as_view()),
    path("tracking/patients/<int:patient_id>/", TrackingPatientDetailView.as_view()),
    *router.urls,
]
