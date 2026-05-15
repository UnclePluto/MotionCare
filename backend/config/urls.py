from django.contrib import admin
from django.urls import include, path

from apps.accounts.auth_views import MeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.auth_urls")),
    path("api/me/", MeView.as_view(), name="me"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/patients/", include("apps.patients.urls")),
    path("api/studies/", include("apps.studies.urls")),
    path("api/visits/", include("apps.visits.urls")),
    path("api/prescriptions/", include("apps.prescriptions.urls")),
    path("api/training/", include("apps.training.urls")),
    path("api/patient-sim/", include("apps.training.patient_sim_urls")),
    path("api/patient-app/", include("apps.patient_app.urls")),
    path("api/health/", include("apps.health.urls")),
    path("api/crf/", include("apps.crf.urls")),
]
