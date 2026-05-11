from rest_framework.routers import DefaultRouter

from .views import ProjectPatientViewSet, StudyGroupViewSet, StudyProjectViewSet

router = DefaultRouter()
router.register("projects", StudyProjectViewSet, basename="study-project")
router.register("groups", StudyGroupViewSet, basename="study-group")
router.register("project-patients", ProjectPatientViewSet, basename="project-patient")

urlpatterns = router.urls

