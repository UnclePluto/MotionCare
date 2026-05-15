import re

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.patient_app.authentication import PatientAppTokenAuthentication
from apps.patient_app.models import PatientAppBindingCode
from apps.patient_app import services
from apps.patient_app.services import (
    bind_project_patient_with_code,
    create_binding_code,
    hash_patient_app_token,
    revoke_project_patient_binding,
)


@pytest.mark.django_db
def test_create_binding_code_returns_plain_code_and_stores_hash_only(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient, created_by=doctor)

    assert re.fullmatch(r"[0-9]{4}", plain_code)
    assert binding.project_patient == project_patient
    assert binding.created_by == doctor
    assert binding.code_hash
    assert binding.code_hash != plain_code
    assert not PatientAppBindingCode.objects.filter(code_hash=plain_code).exists()
    assert binding.used_at is None
    assert binding.revoked_at is None
    assert abs(
        binding.expires_at - (binding.created_at + timezone.timedelta(minutes=15))
    ) <= timezone.timedelta(seconds=2)


@pytest.mark.django_db
def test_bind_project_patient_with_code_creates_session_and_marks_code_used(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient, created_by=doctor)

    token, session = bind_project_patient_with_code(plain_code.lower(), wx_openid="openid-001")

    binding.refresh_from_db()
    assert token
    assert session.project_patient == project_patient
    assert session.patient == project_patient.patient
    assert session.wx_openid == "openid-001"
    assert session.is_active is True
    assert session.token_hash == hash_patient_app_token(token)
    assert session.token_hash != token
    assert binding.used_at is not None


@pytest.mark.django_db
def test_binding_code_cannot_be_reused(project_patient, doctor):
    plain_code, _ = create_binding_code(project_patient, created_by=doctor)
    bind_project_patient_with_code(plain_code, wx_openid="openid-001")

    with pytest.raises(ValidationError, match="绑定码已使用"):
        bind_project_patient_with_code(plain_code, wx_openid="openid-002")


@pytest.mark.django_db
def test_invalid_binding_code_is_rejected():
    with pytest.raises(ValidationError, match="绑定码无效"):
        bind_project_patient_with_code("12AB", wx_openid="openid-001")


@pytest.mark.django_db
def test_mixed_character_binding_code_is_not_filtered_to_valid_code(
    project_patient,
    doctor,
    monkeypatch,
):
    monkeypatch.setattr(services, "_generate_binding_code", lambda: "1234")
    _, binding = create_binding_code(project_patient, created_by=doctor)

    with pytest.raises(ValidationError, match="绑定码无效"):
        bind_project_patient_with_code("1a2b3c4d", wx_openid="openid-001")

    binding.refresh_from_db()
    assert binding.used_at is None


@pytest.mark.parametrize("invalid_code", [" 1234 ", "\t1234\n", 1234])
@pytest.mark.django_db
def test_binding_code_with_whitespace_or_non_string_is_rejected_without_binding(
    project_patient,
    doctor,
    monkeypatch,
    invalid_code,
):
    monkeypatch.setattr(services, "_generate_binding_code", lambda: "1234")
    _, binding = create_binding_code(project_patient, created_by=doctor)

    with pytest.raises(ValidationError, match="绑定码无效"):
        bind_project_patient_with_code(invalid_code, wx_openid="openid-001")

    binding.refresh_from_db()
    assert binding.used_at is None


@pytest.mark.django_db
def test_expired_binding_code_is_rejected(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient, created_by=doctor)
    binding.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    binding.save(update_fields=["expires_at"])

    with pytest.raises(ValidationError, match="绑定码已过期"):
        bind_project_patient_with_code(plain_code, wx_openid="openid-001")


@pytest.mark.django_db
def test_revoked_binding_code_is_rejected(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient, created_by=doctor)
    binding.revoked_at = timezone.now()
    binding.save(update_fields=["revoked_at"])

    with pytest.raises(ValidationError, match="绑定码已撤销"):
        bind_project_patient_with_code(plain_code, wx_openid="openid-001")


@pytest.mark.django_db
def test_create_binding_code_revokes_old_unused_code(project_patient, doctor):
    _, old_binding = create_binding_code(project_patient, created_by=doctor)
    stale_updated_at = timezone.now() - timezone.timedelta(days=1)
    PatientAppBindingCode.objects.filter(pk=old_binding.pk).update(updated_at=stale_updated_at)

    _, new_binding = create_binding_code(project_patient, created_by=doctor)

    old_binding.refresh_from_db()
    assert old_binding.revoked_at is not None
    assert old_binding.updated_at >= old_binding.revoked_at
    assert new_binding.revoked_at is None


@pytest.mark.django_db
def test_expired_numeric_binding_code_can_be_reused(project_patient, doctor, monkeypatch):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient, StudyGroup, StudyProject

    second_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    second_project = StudyProject.objects.create(name="认知衰弱研究二", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="干预组", target_ratio=1)
    second_project_patient = ProjectPatient.objects.create(
        project=second_project,
        patient=second_patient,
        group=second_group,
    )

    monkeypatch.setattr(services, "_generate_binding_code", lambda: "0387")
    first_code, first_binding = create_binding_code(project_patient, created_by=doctor)
    PatientAppBindingCode.objects.filter(pk=first_binding.pk).update(
        expires_at=timezone.now() - timezone.timedelta(seconds=1)
    )

    second_code, second_binding = create_binding_code(second_project_patient, created_by=doctor)

    first_binding.refresh_from_db()
    _, session = bind_project_patient_with_code(second_code, wx_openid="openid-002")
    assert first_code == "0387"
    assert second_code == "0387"
    assert first_binding.revoked_at is not None
    assert second_binding.project_patient == second_project_patient
    assert session.project_patient == second_project_patient


@pytest.mark.django_db
def test_active_numeric_binding_code_collision_retries(project_patient, doctor, monkeypatch):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient, StudyGroup, StudyProject

    second_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    second_project = StudyProject.objects.create(name="认知衰弱研究二", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="干预组", target_ratio=1)
    second_project_patient = ProjectPatient.objects.create(
        project=second_project,
        patient=second_patient,
        group=second_group,
    )

    codes = iter(["0387", "4912"])
    monkeypatch.setattr(services, "_generate_binding_code", lambda: next(codes))
    first_code, _ = create_binding_code(project_patient, created_by=doctor)

    second_code, second_binding = create_binding_code(second_project_patient, created_by=doctor)

    assert first_code == "0387"
    assert second_code == "4912"
    assert second_binding.project_patient == second_project_patient


@pytest.mark.django_db
def test_active_binding_code_hash_is_unique_at_database_level(project_patient, doctor):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient, StudyGroup, StudyProject

    second_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    second_project = StudyProject.objects.create(name="认知衰弱研究二", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="干预组", target_ratio=1)
    second_project_patient = ProjectPatient.objects.create(
        project=second_project,
        patient=second_patient,
        group=second_group,
    )
    expires_at = timezone.now() + timezone.timedelta(minutes=15)
    first_binding = PatientAppBindingCode.objects.create(
        project_patient=project_patient,
        code_hash=services._hash_binding_code("0387"),
        expires_at=expires_at,
        created_by=doctor,
    )

    with pytest.raises(IntegrityError):
        PatientAppBindingCode.objects.create(
            project_patient=second_project_patient,
            code_hash=first_binding.code_hash,
            expires_at=expires_at,
            created_by=doctor,
        )


@pytest.mark.django_db
def test_create_binding_code_raises_after_fixed_retry_collisions(
    project_patient,
    doctor,
    monkeypatch,
):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient, StudyGroup, StudyProject

    second_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    second_project = StudyProject.objects.create(name="认知衰弱研究二", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="干预组", target_ratio=1)
    second_project_patient = ProjectPatient.objects.create(
        project=second_project,
        patient=second_patient,
        group=second_group,
    )
    existing_code, _ = create_binding_code(project_patient, created_by=doctor)
    monkeypatch.setattr(services, "_generate_binding_code", lambda: existing_code)

    with pytest.raises(ValidationError, match="绑定码生成失败，请重试"):
        create_binding_code(second_project_patient, created_by=doctor)


@pytest.mark.django_db
def test_create_binding_code_retries_when_unique_race_raises_integrity_error(
    project_patient,
    doctor,
    monkeypatch,
):
    original_create = PatientAppBindingCode.objects.create
    calls = {"count": 0}

    def create_with_one_collision(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise IntegrityError("duplicate code_hash")
        return original_create(*args, **kwargs)

    monkeypatch.setattr(PatientAppBindingCode.objects, "create", create_with_one_collision)

    plain_code, binding = create_binding_code(project_patient, created_by=doctor)

    assert plain_code
    assert binding.pk
    assert binding.project_patient == project_patient
    assert calls["count"] == 2


@pytest.mark.django_db
def test_binding_with_new_code_deactivates_old_active_session(project_patient, doctor):
    first_code, _ = create_binding_code(project_patient, created_by=doctor)
    _, old_session = bind_project_patient_with_code(first_code, wx_openid="openid-001")
    stale_updated_at = timezone.now() - timezone.timedelta(days=1)
    type(old_session).objects.filter(pk=old_session.pk).update(updated_at=stale_updated_at)
    second_code, _ = create_binding_code(project_patient, created_by=doctor)

    _, new_session = bind_project_patient_with_code(second_code, wx_openid="openid-002")

    old_session.refresh_from_db()
    assert old_session.is_active is False
    assert old_session.updated_at > stale_updated_at
    assert new_session.is_active is True


@pytest.mark.django_db
def test_hash_patient_app_token_does_not_return_plain_token():
    token = "plain-token"

    token_hash = hash_patient_app_token(token)

    assert token_hash
    assert token_hash != token


@pytest.mark.django_db
def test_patient_app_token_authentication_accepts_active_session_and_updates_last_seen(
    project_patient,
    doctor,
):
    plain_code, _ = create_binding_code(project_patient, created_by=doctor)
    token, session = bind_project_patient_with_code(plain_code, wx_openid="openid-001")
    assert session.last_seen_at is None
    request = Request(
        APIRequestFactory().get(
            "/api/patient-app/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
    )

    principal, authenticated_session = PatientAppTokenAuthentication().authenticate(request)

    session.refresh_from_db()
    assert principal.is_authenticated is True
    assert principal.session == session
    assert principal.project_patient == project_patient
    assert principal.patient == project_patient.patient
    assert authenticated_session == session
    assert session.last_seen_at is not None


@pytest.mark.django_db
def test_patient_app_token_authentication_rejects_bad_format():
    request = Request(
        APIRequestFactory().get(
            "/api/patient-app/me/",
            HTTP_AUTHORIZATION="Token abc",
        )
    )

    with pytest.raises(AuthenticationFailed, match="患者端认证格式错误"):
        PatientAppTokenAuthentication().authenticate(request)


@pytest.mark.django_db
def test_patient_app_token_authentication_rejects_inactive_session(project_patient, doctor):
    plain_code, _ = create_binding_code(project_patient, created_by=doctor)
    token, session = bind_project_patient_with_code(plain_code, wx_openid="openid-001")
    session.is_active = False
    session.save(update_fields=["is_active"])
    request = Request(
        APIRequestFactory().get(
            "/api/patient-app/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
    )

    with pytest.raises(AuthenticationFailed, match="患者端登录已失效"):
        PatientAppTokenAuthentication().authenticate(request)


@pytest.mark.django_db
def test_revoke_project_patient_binding_revokes_codes_and_deactivates_sessions(
    project_patient,
    doctor,
):
    plain_code, used_binding = create_binding_code(project_patient, created_by=doctor)
    _, session = bind_project_patient_with_code(plain_code, wx_openid="openid-001")
    unused_code, unused_binding = create_binding_code(project_patient, created_by=doctor)
    stale_session_updated_at = timezone.now() - timezone.timedelta(days=1)
    type(session).objects.filter(pk=session.pk).update(updated_at=stale_session_updated_at)

    revoke_project_patient_binding(project_patient)

    used_binding.refresh_from_db()
    unused_binding.refresh_from_db()
    session.refresh_from_db()
    assert used_binding.revoked_at is None
    assert unused_binding.revoked_at is not None
    assert unused_binding.updated_at >= unused_binding.revoked_at
    assert session.is_active is False
    assert session.updated_at > stale_session_updated_at
    assert unused_code
