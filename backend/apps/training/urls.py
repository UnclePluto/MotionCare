from rest_framework.routers import DefaultRouter

from .views import TrainingRecordViewSet

router = DefaultRouter()
router.register("", TrainingRecordViewSet, basename="training-record")
urlpatterns = router.urls

