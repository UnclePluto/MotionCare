from rest_framework.routers import DefaultRouter

from .views import VisitRecordViewSet

router = DefaultRouter()
router.register("", VisitRecordViewSet, basename="visit")
urlpatterns = router.urls

