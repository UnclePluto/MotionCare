import pytest

from apps.accounts.models import User


@pytest.mark.django_db
def test_user_uses_phone_as_unique_login_identifier():
    user = User.objects.create_user(
        phone="13800000000",
        password="pass123456",
        name="张医生",
        role=User.Role.DOCTOR,
    )

    assert user.username == "13800000000"
    assert user.phone == "13800000000"
    assert user.name == "张医生"
    assert user.role == User.Role.DOCTOR
    assert user.check_password("pass123456")


@pytest.mark.django_db
def test_create_superuser_sets_super_admin_role():
    user = User.objects.create_superuser(
        phone="13900000000",
        password="pass123456",
        name="超级管理员",
    )

    assert user.is_staff
    assert user.is_superuser
    assert user.role == User.Role.SUPER_ADMIN

