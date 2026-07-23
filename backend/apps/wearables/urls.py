from django.urls import path

from .views import (
    ProjectPatientBindingStatusView,
    ProjectPatientBindView,
    PatientConfigureView,
    PatientMeasureView,
    PatientSyncView,
    WearableBindingUnbindView,
    WearableDeviceDetailView,
    WearableDeviceListCreateView,
    WearableDeviceRingView,
    WearableDeviceStatusView,
)

urlpatterns = [
    path("devices/", WearableDeviceListCreateView.as_view(), name="wearable-device-list"),
    path("devices/<int:pk>/", WearableDeviceDetailView.as_view(), name="wearable-device-detail"),
    path(
        "devices/<int:pk>/check-status/",
        WearableDeviceStatusView.as_view(),
        name="wearable-device-check-status",
    ),
    path("devices/<int:pk>/ring/", WearableDeviceRingView.as_view(), name="wearable-device-ring"),
    path("patients/<int:patient_id>/measure/", PatientMeasureView.as_view(), name="wearable-patient-measure"),
    path(
        "patients/<int:patient_id>/configure/",
        PatientConfigureView.as_view(),
        name="wearable-patient-configure",
    ),
    path("patients/<int:patient_id>/sync/", PatientSyncView.as_view(), name="wearable-patient-sync"),
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
