from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class MotionCareUserManager(UserManager):
    def create_user(self, phone: str, password: str | None = None, **extra_fields):
        if not phone:
            raise ValueError("手机号不能为空")
        extra_fields.setdefault("username", phone)
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPER_ADMIN)
        return self.create_user(phone=phone, password=password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "超级管理员"
        ADMIN = "admin", "管理员"
        DOCTOR = "doctor", "医生"

    class Gender(models.TextChoices):
        MALE = "male", "男"
        FEMALE = "female", "女"
        UNKNOWN = "unknown", "未知"

    phone = models.CharField("手机号", max_length=20, unique=True)
    name = models.CharField("姓名", max_length=80)
    gender = models.CharField("性别", max_length=16, choices=Gender.choices, default=Gender.UNKNOWN)
    role = models.CharField("角色", max_length=32, choices=Role.choices, default=Role.DOCTOR)
    must_change_password = models.BooleanField("是否必须修改密码", default=False)

    objects = MotionCareUserManager()
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    def save(self, *args, **kwargs):
        if self.phone:
            self.username = self.phone
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name}（{self.phone}）"
