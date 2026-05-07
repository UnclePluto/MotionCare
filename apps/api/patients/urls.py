from django.urls import path

from .views import list_patients

urlpatterns = [
    path("", list_patients),
]

