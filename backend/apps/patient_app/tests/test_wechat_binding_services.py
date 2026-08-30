import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.patient_app.models import (
    PatientAppSession,
    PatientAppWechatBinding,
)
from apps.patient_app.services import (
    PatientAppBindingConflict,
    bind_project_patient_with_code,
    create_binding_code,
    hash_patient_app_token,
    recover_patient_app_session,
    revoke_project_patient_binding,
)
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


def create_second_project_patient(doctor):
    patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900009999",
        primary_doctor=doctor,
    )
    project = StudyProject.objects.create(name="微信绑定测试项目", created_by=doctor)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)


def create_patient_app_session(
    project_patient,
    *,
    token: str,
    wx_openid: str | None = None,
    expires_at=None,
):
    return PatientAppSession.objects.create(
        project_patient=project_patient,
        patient=project_patient.patient,
        wx_openid=wx_openid,
        token_hash=hash_patient_app_token(token),
        expires_at=expires_at or timezone.now() + timezone.timedelta(days=30),
    )


@pytest.mark.django_db
def test_wechat_binding_is_unique_on_both_openid_and_project_patient(
    project_patient,
    doctor,
):
    second_project_patient = create_second_project_patient(doctor)
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PatientAppWechatBinding.objects.create(
            project_patient=second_project_patient,
            wx_openid="openid-001",
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        PatientAppWechatBinding.objects.create(
            project_patient=project_patient,
            wx_openid="openid-002",
        )


@pytest.mark.django_db
def test_bound_openid_without_token_receives_new_session(project_patient):
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token=None,
    )

    assert result.status == "authenticated"
    assert result.token
    assert result.session.project_patient == project_patient


@pytest.mark.django_db
def test_expired_token_is_replaced_from_persistent_openid_binding(project_patient):
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    expired_session = create_patient_app_session(
        project_patient,
        token="expired-token",
        expires_at=timezone.now() - timezone.timedelta(seconds=1),
    )
    before_recovery = timezone.now()

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token="expired-token",
    )

    expired_session.refresh_from_db()
    assert result.status == "authenticated"
    assert result.token
    assert result.session != expired_session
    assert result.session.project_patient == project_patient
    assert expired_session.is_active is False
    assert before_recovery + timezone.timedelta(days=30) <= result.session.expires_at
    assert result.session.expires_at <= timezone.now() + timezone.timedelta(days=30)


@pytest.mark.django_db
def test_valid_matching_token_is_kept_and_legacy_openid_is_backfilled(project_patient):
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    session = create_patient_app_session(project_patient, token="matching-token")

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token="matching-token",
    )

    session.refresh_from_db()
    assert result.status == "authenticated"
    assert result.token is None
    assert result.session == session
    assert session.wx_openid == "openid-001"
    assert session.is_active is True


@pytest.mark.django_db
def test_valid_legacy_token_claims_unbound_openid(project_patient):
    session = create_patient_app_session(project_patient, token="legacy-token")

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token="legacy-token",
    )

    session.refresh_from_db()
    assert result.status == "authenticated"
    assert result.token is None
    assert result.session == session
    assert session.wx_openid == "openid-001"
    assert (
        PatientAppWechatBinding.objects.get(wx_openid="openid-001").project_patient
        == project_patient
    )


@pytest.mark.django_db
def test_persistent_openid_binding_wins_over_conflicting_legacy_token(
    project_patient,
    doctor,
):
    token_project_patient = create_second_project_patient(doctor)
    persistent_binding = PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    conflicting_session = create_patient_app_session(
        token_project_patient,
        token="conflicting-token",
    )

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token="conflicting-token",
    )

    persistent_binding.refresh_from_db()
    conflicting_session.refresh_from_db()
    assert result.status == "authenticated"
    assert result.token
    assert result.session.project_patient == project_patient
    assert persistent_binding.project_patient == project_patient
    assert not PatientAppWechatBinding.objects.filter(
        project_patient=token_project_patient
    ).exists()
    assert conflicting_session.project_patient == token_project_patient


@pytest.mark.django_db
def test_legacy_token_cannot_take_project_patient_bound_to_other_openid(project_patient):
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-other",
    )
    session = create_patient_app_session(project_patient, token="legacy-token")

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token="legacy-token",
    )

    session.refresh_from_db()
    assert result.status == "unbound"
    assert result.token is None
    assert result.session is None
    assert session.is_active is True
    assert (
        PatientAppWechatBinding.objects.get(project_patient=project_patient).wx_openid
        == "openid-other"
    )


@pytest.mark.django_db
def test_unbound_openid_without_valid_token_returns_unbound(project_patient):
    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token=None,
    )

    assert result.status == "unbound"
    assert result.token is None
    assert result.session is None
    assert not PatientAppWechatBinding.objects.exists()


@pytest.mark.django_db
def test_binding_new_project_replaces_both_sides_and_deactivates_sessions(
    project_patient,
    doctor,
):
    target_project_patient = create_second_project_patient(doctor)
    source_binding = PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    target_binding = PatientAppWechatBinding.objects.create(
        project_patient=target_project_patient,
        wx_openid="openid-other",
    )
    source_session = create_patient_app_session(
        project_patient,
        token="source-token",
        wx_openid="openid-001",
    )
    target_session = create_patient_app_session(
        target_project_patient,
        token="target-token",
        wx_openid="openid-other",
    )
    code, _ = create_binding_code(target_project_patient, created_by=doctor)

    token, new_session = bind_project_patient_with_code(code, wx_openid="openid-001")

    source_session.refresh_from_db()
    target_session.refresh_from_db()
    assert token
    assert new_session.project_patient == target_project_patient
    assert new_session.wx_openid == "openid-001"
    assert not PatientAppWechatBinding.objects.filter(pk=source_binding.pk).exists()
    assert not PatientAppWechatBinding.objects.filter(pk=target_binding.pk).exists()
    assert (
        PatientAppWechatBinding.objects.get(wx_openid="openid-001").project_patient
        == target_project_patient
    )
    assert source_session.is_active is False
    assert target_session.is_active is False
    assert ProjectPatient.objects.filter(pk=project_patient.pk).exists()
    assert ProjectPatient.objects.filter(pk=target_project_patient.pk).exists()


@pytest.mark.django_db
def test_revoke_deletes_wechat_binding_and_deactivates_sessions(project_patient):
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    create_patient_app_session(
        project_patient,
        token="active-token",
        wx_openid="openid-001",
    )

    revoke_project_patient_binding(project_patient)

    assert not PatientAppWechatBinding.objects.filter(project_patient=project_patient).exists()
    assert not PatientAppSession.objects.filter(
        project_patient=project_patient,
        is_active=True,
    ).exists()


@pytest.mark.django_db
def test_binding_failure_rolls_back_code_consumption_and_relationship_changes(
    project_patient,
    doctor,
    monkeypatch,
):
    target_project_patient = create_second_project_patient(doctor)
    source_binding = PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    target_binding = PatientAppWechatBinding.objects.create(
        project_patient=target_project_patient,
        wx_openid="openid-other",
    )
    source_session = create_patient_app_session(
        project_patient,
        token="source-token",
        wx_openid="openid-001",
    )
    target_session = create_patient_app_session(
        target_project_patient,
        token="target-token",
        wx_openid="openid-other",
    )
    code, binding_code = create_binding_code(target_project_patient, created_by=doctor)

    def raise_integrity_error(*args, **kwargs):
        raise IntegrityError("duplicate persistent binding")

    monkeypatch.setattr(PatientAppWechatBinding.objects, "create", raise_integrity_error)

    with pytest.raises(PatientAppBindingConflict):
        bind_project_patient_with_code(code, wx_openid="openid-001")

    binding_code.refresh_from_db()
    source_binding.refresh_from_db()
    target_binding.refresh_from_db()
    source_session.refresh_from_db()
    target_session.refresh_from_db()
    assert binding_code.used_at is None
    assert source_binding.wx_openid == "openid-001"
    assert source_binding.project_patient == project_patient
    assert target_binding.wx_openid == "openid-other"
    assert target_binding.project_patient == target_project_patient
    assert source_session.is_active is True
    assert target_session.is_active is True
