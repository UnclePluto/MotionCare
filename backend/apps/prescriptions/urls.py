from rest_framework.routers import DefaultRouter

from .views import ActionLibraryItemViewSet, PrescriptionActionViewSet, PrescriptionViewSet

router = DefaultRouter()
router.register("actions", ActionLibraryItemViewSet, basename="action-library-item")
router.register("prescription-actions", PrescriptionActionViewSet, basename="prescription-action")
router.register("", PrescriptionViewSet, basename="prescription")

urlpatterns = router.urls

