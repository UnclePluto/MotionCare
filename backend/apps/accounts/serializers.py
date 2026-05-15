import re

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User

DEFAULT_DOCTOR_PASSWORD = "888888"
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class UserSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "name",
            "gender",
            "role",
            "date_joined",
            "must_change_password",
            "is_active",
        ]
        read_only_fields = ["id", "role", "date_joined", "must_change_password", "is_active"]

    def validate_phone(self, value: str) -> str:
        phone = value.strip()
        if not PHONE_RE.match(phone):
            raise serializers.ValidationError("请输入 11 位有效手机号")
        qs = User.objects.filter(phone=phone)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("该手机号已存在")
        return phone

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("请输入姓名")
        return name

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(
            phone=validated_data["phone"],
            password=DEFAULT_DOCTOR_PASSWORD,
            name=validated_data["name"],
            gender=validated_data.get("gender", User.Gender.UNKNOWN),
            role=User.Role.DOCTOR,
            must_change_password=True,
        )

    def update(self, instance: User, validated_data: dict) -> User:
        for field in ("name", "gender", "phone"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        old_password = attrs["old_password"]
        new_password = attrs["new_password"]
        confirm_password = attrs["confirm_password"]

        if not user.check_password(old_password):
            raise serializers.ValidationError({"old_password": "原密码错误"})
        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "两次输入的新密码不一致"})
        if new_password == DEFAULT_DOCTOR_PASSWORD:
            raise serializers.ValidationError({"new_password": "新密码不能使用默认密码"})
        validate_password(new_password, user=user)
        return attrs
