from rest_framework.routers import DefaultRouter

from .views import DailyHealthRecordViewSet

router = DefaultRouter()
router.register("", DailyHealthRecordViewSet, basename="daily-health-record")
urlpatterns = router.urls

