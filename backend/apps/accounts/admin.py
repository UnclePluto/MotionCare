from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class MotionCareUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("MotionCare", {"fields": ("phone", "name", "gender", "role", "must_change_password")}),
    )
    list_display = ("phone", "name", "gender", "role", "must_change_password", "is_active", "is_staff")
    search_fields = ("phone", "name")
