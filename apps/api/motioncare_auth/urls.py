from django.urls import path

from .views import csrf, login_view

urlpatterns = [
    path("csrf", csrf),
    path("login", login_view),
]

