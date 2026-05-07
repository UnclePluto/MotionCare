from rest_framework.routers import DefaultRouter

from .views import CrfViewSet

router = DefaultRouter()
router.register("project-patients", CrfViewSet, basename="crf-project-patient")
urlpatterns = router.urls

