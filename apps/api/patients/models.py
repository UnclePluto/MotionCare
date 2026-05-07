from django.db import models


class Patient(models.Model):
    name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

