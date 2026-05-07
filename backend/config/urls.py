from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/patients/", include("apps.patients.urls")),
    path("api/studies/", include("apps.studies.urls")),
    path("api/visits/", include("apps.visits.urls")),
    path("api/prescriptions/", include("apps.prescriptions.urls")),
    path("api/training/", include("apps.training.urls")),
    path("api/health/", include("apps.health.urls")),
    path("api/crf/", include("apps.crf.urls")),
]

