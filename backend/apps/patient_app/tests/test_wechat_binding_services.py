import threading
import uuid

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.patient_app import services
from apps.patient_app.authentication import PatientAppTokenAuthentication
from apps.patient_app.models import (
    PatientAppBindingCode,
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
from apps.accounts.models import User
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


def postgres_integrity_error(constraint_name: str) -> IntegrityError:
    class FakePostgresUniqueViolation(Exception):
        def __init__(self):
            self.diag = type("Diag", (), {"constraint_name": constraint_name})()

    try:
        raise IntegrityError("duplicate key") from FakePostgresUniqueViolation()
    except IntegrityError as error:
        return error


def start_database_thread(name, operation, results, errors, completed):
    def runner():
        close_old_connections()
        try:
            results[name] = operation()
        except Exception as exc:  # pragma: no cover - surfaced by parent assertions
            errors[name] = exc
        finally:
            completed[name].set()
            close_old_connections()

    return threading.Thread(target=runner, name=name)


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
def test_valid_matching_token_keeps_nonempty_session_openid_audit_value(project_patient):
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )
    session = create_patient_app_session(
        project_patient,
        token="matching-token",
        wx_openid="historical-audit-openid",
    )

    result = recover_patient_app_session(
        wx_openid="openid-001",
        presented_token="matching-token",
    )

    session.refresh_from_db()
    assert result.status == "authenticated"
    assert result.token is None
    assert result.session == session
    assert session.wx_openid == "historical-audit-openid"


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
    source_legacy_session = create_patient_app_session(
        project_patient,
        token="source-legacy-token",
        wx_openid=None,
    )
    target_session = create_patient_app_session(
        target_project_patient,
        token="target-token",
        wx_openid="openid-other",
    )
    code, _ = create_binding_code(target_project_patient, created_by=doctor)

    token, new_session = bind_project_patient_with_code(code, wx_openid="openid-001")

    source_session.refresh_from_db()
    source_legacy_session.refresh_from_db()
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
    assert source_legacy_session.is_active is False
    assert target_session.is_active is False
    assert ProjectPatient.objects.filter(pk=project_patient.pk).exists()
    assert ProjectPatient.objects.filter(pk=target_project_patient.pk).exists()


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="需要 PostgreSQL 双连接验证换绑行锁交错",
)
def test_concurrent_rebind_does_not_deactivate_source_that_moved_to_another_openid(
    django_db_setup,
    django_db_blocker,
    monkeypatch,
):
    del django_db_setup
    database_name = str(connection.settings_dict["NAME"])
    if not database_name.startswith("test_"):
        raise RuntimeError("并发换绑测试拒绝在非 test_ 数据库运行")

    created_ids = {
        "doctor": None,
        "patients": [],
        "project": None,
        "group": None,
        "project_patients": [],
    }
    move_source = None
    bind_target = None

    with django_db_blocker.unblock():
        try:
            unique_number = uuid.uuid4().int % 1_000_000_000
            unique_suffix = f"{unique_number:09d}"
            doctor = User.objects.create_user(
                phone=f"17{unique_suffix}",
                password="pass123456",
                name=f"并发换绑医生-{unique_suffix}",
                role=User.Role.DOCTOR,
            )
            created_ids["doctor"] = doctor.pk
            source_patient = Patient.objects.create(
                name=f"并发源患者-{unique_suffix}",
                gender=Patient.Gender.MALE,
                age=70,
                phone=f"18{unique_suffix}",
                primary_doctor=doctor,
            )
            target_patient = Patient.objects.create(
                name=f"并发目标患者-{unique_suffix}",
                gender=Patient.Gender.FEMALE,
                age=68,
                phone=f"19{unique_suffix}",
                primary_doctor=doctor,
            )
            created_ids["patients"] = [source_patient.pk, target_patient.pk]
            project = StudyProject.objects.create(
                name=f"并发换绑项目-{unique_suffix}",
                created_by=doctor,
            )
            created_ids["project"] = project.pk
            group = StudyGroup.objects.create(
                project=project,
                name="并发组",
                target_ratio=1,
            )
            created_ids["group"] = group.pk
            source_project_patient = ProjectPatient.objects.create(
                project=project,
                patient=source_patient,
                group=group,
            )
            target_project_patient = ProjectPatient.objects.create(
                project=project,
                patient=target_patient,
                group=group,
            )
            created_ids["project_patients"] = [
                source_project_patient.pk,
                target_project_patient.pk,
            ]
            PatientAppWechatBinding.objects.create(
                project_patient=source_project_patient,
                wx_openid="openid-current",
            )
            source_code, _ = create_binding_code(
                source_project_patient,
                created_by=doctor,
            )
            target_code, _ = create_binding_code(
                target_project_patient,
                created_by=doctor,
            )
            project_patient_lock_started = {
                "move-source": threading.Event(),
                "bind-target": threading.Event(),
            }
            completed = {
                "move-source": threading.Event(),
                "bind-target": threading.Event(),
            }
            results = {}
            errors = {}
            original_fetch_all = QuerySet._fetch_all

            def observe_project_patient_lock(queryset):
                thread_name = threading.current_thread().name
                if (
                    thread_name in project_patient_lock_started
                    and queryset.model is ProjectPatient
                    and queryset.query.select_for_update
                ):
                    project_patient_lock_started[thread_name].set()
                return original_fetch_all(queryset)

            move_source = start_database_thread(
                "move-source",
                lambda: bind_project_patient_with_code(
                    source_code,
                    wx_openid="openid-moved",
                ),
                results,
                errors,
                completed,
            )
            bind_target = start_database_thread(
                "bind-target",
                lambda: bind_project_patient_with_code(
                    target_code,
                    wx_openid="openid-current",
                ),
                results,
                errors,
                completed,
            )

            monkeypatch.setattr(QuerySet, "_fetch_all", observe_project_patient_lock)
            with transaction.atomic():
                ProjectPatient.objects.select_for_update().get(pk=source_project_patient.pk)
                move_source.start()
                assert project_patient_lock_started["move-source"].wait(timeout=10)
                assert not completed["move-source"].wait(timeout=0.2)
                bind_target.start()
                assert project_patient_lock_started["bind-target"].wait(timeout=10)
                assert not completed["bind-target"].wait(timeout=0.2)

            move_source.join(timeout=10)
            bind_target.join(timeout=10)
            assert not move_source.is_alive()
            assert not bind_target.is_alive()
            assert errors == {}
            moved_token, moved_session = results["move-source"]
            target_token, target_session = results["bind-target"]
            moved_session.refresh_from_db()
            target_session.refresh_from_db()
            assert moved_token
            assert target_token
            assert (
                PatientAppWechatBinding.objects.get(
                    project_patient=source_project_patient
                ).wx_openid
                == "openid-moved"
            )
            assert (
                PatientAppWechatBinding.objects.get(
                    project_patient=target_project_patient
                ).wx_openid
                == "openid-current"
            )
            assert moved_session.is_active is True
            assert target_session.is_active is True

            request = Request(
                APIRequestFactory().get(
                    "/api/patient-app/me/",
                    HTTP_AUTHORIZATION=f"Bearer {moved_token}",
                )
            )
            principal, authenticated_session = PatientAppTokenAuthentication().authenticate(request)
            assert principal.project_patient == source_project_patient
            assert authenticated_session == moved_session
        finally:
            for database_thread in (move_source, bind_target):
                if database_thread is not None and database_thread.ident is not None:
                    database_thread.join(timeout=10)
            project_patient_ids = created_ids["project_patients"]
            if project_patient_ids:
                PatientAppSession.objects.filter(
                    project_patient_id__in=project_patient_ids
                ).delete()
                PatientAppWechatBinding.objects.filter(
                    project_patient_id__in=project_patient_ids
                ).delete()
                PatientAppBindingCode.objects.filter(
                    project_patient_id__in=project_patient_ids
                ).delete()
                ProjectPatient.objects.filter(pk__in=project_patient_ids).delete()
            if created_ids["group"] is not None:
                StudyGroup.objects.filter(pk=created_ids["group"]).delete()
            if created_ids["project"] is not None:
                StudyProject.objects.filter(pk=created_ids["project"]).delete()
            if created_ids["patients"]:
                Patient.objects.filter(pk__in=created_ids["patients"]).delete()
            if created_ids["doctor"] is not None:
                User.objects.filter(pk=created_ids["doctor"]).delete()


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


@pytest.mark.parametrize("sqlite_column", ["wx_openid", "project_patient_id"])
@pytest.mark.django_db
def test_binding_failure_rolls_back_code_consumption_and_relationship_changes(
    project_patient,
    doctor,
    monkeypatch,
    sqlite_column,
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
        raise IntegrityError(
            f"UNIQUE constraint failed: patient_app_patientappwechatbinding.{sqlite_column}"
        )

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


@pytest.mark.django_db
def test_unknown_integrity_error_is_not_mapped_to_binding_conflict(
    project_patient,
    doctor,
    monkeypatch,
):
    code, binding_code = create_binding_code(project_patient, created_by=doctor)

    def raise_integrity_error(*args, **kwargs):
        raise IntegrityError("CHECK constraint failed: unrelated_check")

    monkeypatch.setattr(PatientAppWechatBinding.objects, "create", raise_integrity_error)

    with pytest.raises(IntegrityError, match="unrelated_check"):
        bind_project_patient_with_code(code, wx_openid="openid-001")

    binding_code.refresh_from_db()
    assert binding_code.used_at is None


@pytest.mark.django_db
def test_recovery_does_not_map_unknown_integrity_error_to_binding_conflict(
    project_patient,
    monkeypatch,
):
    create_patient_app_session(project_patient, token="legacy-token")

    def raise_integrity_error(*args, **kwargs):
        raise IntegrityError("CHECK constraint failed: unrelated_check")

    monkeypatch.setattr(PatientAppWechatBinding.objects, "create", raise_integrity_error)

    with pytest.raises(IntegrityError, match="unrelated_check"):
        recover_patient_app_session(
            wx_openid="openid-001",
            presented_token="legacy-token",
        )

    assert not PatientAppWechatBinding.objects.exists()


@pytest.mark.parametrize(
    "constraint_name",
    [
        "patient_app_patientappwechatbinding_wx_openid_key",
        "patient_app_patientappwechatbinding_project_patient_id_key",
    ],
)
@pytest.mark.django_db
def test_postgresql_binding_unique_constraints_are_mapped_to_binding_conflict(
    project_patient,
    doctor,
    monkeypatch,
    constraint_name,
):
    code, binding_code = create_binding_code(project_patient, created_by=doctor)

    postgres_error = postgres_integrity_error(constraint_name)

    def raise_integrity_error(*args, **kwargs):
        raise postgres_error

    monkeypatch.setattr(PatientAppWechatBinding.objects, "create", raise_integrity_error)

    with pytest.raises(PatientAppBindingConflict):
        bind_project_patient_with_code(code, wx_openid="openid-001")

    binding_code.refresh_from_db()
    assert binding_code.used_at is None


@pytest.mark.django_db
def test_postgresql_session_token_hash_constraint_retries(
    project_patient,
    doctor,
    monkeypatch,
):
    code, _ = create_binding_code(project_patient, created_by=doctor)
    original_create = PatientAppSession.objects.create
    create_attempts = []
    token_constraint_error = postgres_integrity_error(
        "patient_app_patientappsession_token_hash_key"
    )

    def create_with_one_token_collision(*args, **kwargs):
        create_attempts.append(kwargs["token_hash"])
        if len(create_attempts) == 1:
            raise token_constraint_error
        return original_create(*args, **kwargs)

    monkeypatch.setattr(PatientAppSession.objects, "create", create_with_one_token_collision)

    token, session = bind_project_patient_with_code(code, wx_openid="openid-001")

    assert token
    assert session.token_hash == hash_patient_app_token(token)
    assert len(create_attempts) == 2


@pytest.mark.django_db
def test_session_token_hash_collision_retries_without_binding_conflict(
    project_patient,
    doctor,
    monkeypatch,
):
    collided_session = create_patient_app_session(
        project_patient,
        token="collision-token",
    )
    code, _ = create_binding_code(project_patient, created_by=doctor)
    generated_tokens = iter(["collision-token", "fresh-token"])
    monkeypatch.setattr(
        services.secrets,
        "token_urlsafe",
        lambda _length: next(generated_tokens),
    )

    token, session = bind_project_patient_with_code(code, wx_openid="openid-001")

    collided_session.refresh_from_db()
    assert token == "fresh-token"
    assert session.token_hash == hash_patient_app_token("fresh-token")
    assert collided_session.is_active is False


@pytest.mark.django_db
def test_session_token_hash_collision_has_finite_retry_limit(
    project_patient,
    doctor,
    monkeypatch,
):
    create_patient_app_session(project_patient, token="collision-token")
    code, binding_code = create_binding_code(project_patient, created_by=doctor)
    generated_tokens = []

    def generate_colliding_token(_length):
        generated_tokens.append("collision-token")
        return "collision-token"

    monkeypatch.setattr(services.secrets, "token_urlsafe", generate_colliding_token)

    with pytest.raises(IntegrityError, match="patientappsession.token_hash"):
        bind_project_patient_with_code(code, wx_openid="openid-001")

    binding_code.refresh_from_db()
    assert generated_tokens == ["collision-token"] * 3
    assert binding_code.used_at is None
    assert not PatientAppWechatBinding.objects.exists()


@pytest.mark.django_db
def test_binding_locks_project_patients_before_binding_code(
    project_patient,
    doctor,
    monkeypatch,
):
    code, _ = create_binding_code(project_patient, created_by=doctor)
    lock_order = []
    original_select_for_update = QuerySet.select_for_update

    def record_select_for_update(queryset, *args, **kwargs):
        lock_order.append(queryset.model)
        return original_select_for_update(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", record_select_for_update)

    bind_project_patient_with_code(code, wx_openid="openid-001")

    assert lock_order.index(ProjectPatient) < lock_order.index(PatientAppBindingCode)
