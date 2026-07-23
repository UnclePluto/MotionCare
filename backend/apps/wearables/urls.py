from django.urls import path

from .views import (
    ProjectPatientBindingStatusView,
    ProjectPatientBindView,
    WearableBindingUnbindView,
    WearableDeviceDetailView,
    WearableDeviceListCreateView,
)

urlpatterns = [
    path("devices/", WearableDeviceListCreateView.as_view(), name="wearable-device-list"),
    path("devices/<int:pk>/", WearableDeviceDetailView.as_view(), name="wearable-device-detail"),
    path(
        "project-patients/<int:project_patient_id>/binding/",
        ProjectPatientBindingStatusView.as_view(),
        name="wearable-project-patient-binding-status",
    ),
    path(
        "project-patients/<int:project_patient_id>/bind/",
        ProjectPatientBindView.as_view(),
        name="wearable-project-patient-bind",
    ),
    path(
        "bindings/<int:binding_id>/unbind/",
        WearableBindingUnbindView.as_view(),
        name="wearable-binding-unbind",
    ),
]
