import re
import secrets
from dataclasses import dataclass
from typing import Literal

from django.core.exceptions import ValidationError
from django.core.signing import salted_hmac
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.patient_app.models import (
    PatientAppBindingCode,
    PatientAppSession,
    PatientAppWechatBinding,
)
from apps.studies.models import ProjectPatient

BINDING_CODE_ALPHABET = "0123456789"
BINDING_CODE_LENGTH = 4
BINDING_CODE_MAX_ATTEMPTS = 20
BINDING_CODE_TTL = timezone.timedelta(minutes=15)
BINDING_CODE_PATTERN = re.compile(r"^[0-9]{4}$")
SESSION_TTL = timezone.timedelta(days=30)
SESSION_TOKEN_MAX_ATTEMPTS = 3
PATIENT_APP_WECHAT_BINDING_UNIQUE_CONSTRAINTS = frozenset(
    {
        "patient_app_patientappwechatbinding_wx_openid_d8e72b28_uniq",
        "patient_app_patientappwe_project_patient_id_e7c05965_uniq",
    }
)
PATIENT_APP_WECHAT_BINDING_SQLITE_UNIQUE_ERRORS = frozenset(
    {
        "UNIQUE constraint failed: patient_app_patientappwechatbinding.wx_openid",
        "UNIQUE constraint failed: patient_app_patientappwechatbinding.project_patient_id",
    }
)
PATIENT_APP_SESSION_TOKEN_UNIQUE_CONSTRAINT = (
    "patient_app_patientappsession_token_hash_f07ee10f_uniq"
)
PATIENT_APP_SESSION_TOKEN_SQLITE_UNIQUE_ERROR = (
    "UNIQUE constraint failed: patient_app_patientappsession.token_hash"
)


@dataclass(frozen=True)
class PatientAppSessionRecovery:
    status: Literal["authenticated", "unbound"]
    token: str | None
    session: PatientAppSession | None


class PatientAppBindingConflict(Exception):
    pass


def _normalize_binding_code(code: str) -> str:
    return code if isinstance(code, str) else ""


def _hash_binding_code(code: str) -> str:
    return salted_hmac("patient_app.binding_code", _normalize_binding_code(code)).hexdigest()


def hash_patient_app_token(token: str) -> str:
    return salted_hmac("patient_app.session_token", token).hexdigest()


def _integrity_error_constraint_name(exc: IntegrityError) -> str | None:
    cause = exc.__cause__
    return getattr(getattr(cause, "diag", None), "constraint_name", None)


def _is_wechat_binding_unique_conflict(exc: IntegrityError) -> bool:
    constraint_name = _integrity_error_constraint_name(exc)
    if constraint_name is not None:
        return constraint_name in PATIENT_APP_WECHAT_BINDING_UNIQUE_CONSTRAINTS
    return str(exc) in PATIENT_APP_WECHAT_BINDING_SQLITE_UNIQUE_ERRORS


def _is_session_token_unique_conflict(exc: IntegrityError) -> bool:
    constraint_name = _integrity_error_constraint_name(exc)
    if constraint_name is not None:
        return constraint_name == PATIENT_APP_SESSION_TOKEN_UNIQUE_CONSTRAINT
    return str(exc) == PATIENT_APP_SESSION_TOKEN_SQLITE_UNIQUE_ERROR


def _active_session_for_token(token: str | None, now) -> PatientAppSession | None:
    if not token:
        return None
    return (
        PatientAppSession.objects.select_related("project_patient__patient")
        .filter(
            token_hash=hash_patient_app_token(token),
            is_active=True,
            expires_at__gt=now,
        )
        .first()
    )


def _create_patient_app_session(*, project_patient, wx_openid, now):
    last_token_collision = None
    for _ in range(SESSION_TOKEN_MAX_ATTEMPTS):
        token = secrets.token_urlsafe(32)
        try:
            with transaction.atomic():
                session = PatientAppSession.objects.create(
                    project_patient=project_patient,
                    patient=project_patient.patient,
                    wx_openid=wx_openid,
                    token_hash=hash_patient_app_token(token),
                    expires_at=now + SESSION_TTL,
                )
        except IntegrityError as exc:
            if not _is_session_token_unique_conflict(exc):
                raise
            last_token_collision = exc
            continue
        return token, session

    assert last_token_collision is not None
    raise last_token_collision


def _lock_and_deactivate_sessions(*, filters: Q, now) -> None:
    session_ids = list(
        PatientAppSession.objects.select_for_update()
        .filter(filters, is_active=True)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if session_ids:
        PatientAppSession.objects.filter(pk__in=session_ids).update(
            is_active=False,
            updated_at=now,
        )


def _generate_binding_code() -> str:
    return "".join(secrets.choice(BINDING_CODE_ALPHABET) for _ in range(BINDING_CODE_LENGTH))


def create_binding_code(project_patient, created_by=None):
    now = timezone.now()
    expires_at = now + BINDING_CODE_TTL

    with transaction.atomic():
        locked_project_patient = ProjectPatient.objects.select_for_update().get(
            pk=project_patient.pk
        )
        PatientAppBindingCode.objects.select_for_update().filter(
            project_patient=locked_project_patient,
            used_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=now, updated_at=now)

        for _ in range(BINDING_CODE_MAX_ATTEMPTS):
            plain_code = _generate_binding_code()
            code_hash = _hash_binding_code(plain_code)
            PatientAppBindingCode.objects.select_for_update().filter(
                code_hash=code_hash,
                used_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__lte=now,
            ).update(revoked_at=now, updated_at=now)
            active_collision_exists = (
                PatientAppBindingCode.objects.select_for_update()
                .filter(
                    code_hash=code_hash,
                    used_at__isnull=True,
                    revoked_at__isnull=True,
                )
                .exists()
            )
            if active_collision_exists:
                continue
            try:
                with transaction.atomic():
                    binding = PatientAppBindingCode.objects.create(
                        project_patient=locked_project_patient,
                        code_hash=code_hash,
                        expires_at=expires_at,
                        created_by=created_by,
                    )
            except IntegrityError:
                continue
            return plain_code, binding
        else:
            raise ValidationError("绑定码生成失败，请重试")


def recover_patient_app_session(
    *,
    wx_openid: str,
    presented_token: str | None,
) -> PatientAppSessionRecovery:
    now = timezone.now()

    try:
        with transaction.atomic():
            persistent_binding_ref = (
                PatientAppWechatBinding.objects.filter(wx_openid=wx_openid)
                .only("id", "project_patient_id")
                .first()
            )
            active_session_ref = _active_session_for_token(presented_token, now)
            related_project_patient_ids = {
                item_id
                for item_id in (
                    getattr(persistent_binding_ref, "project_patient_id", None),
                    getattr(active_session_ref, "project_patient_id", None),
                )
                if item_id is not None
            }
            locked_project_patients = {
                item.pk: item
                for item in ProjectPatient.objects.select_for_update()
                .select_related("patient")
                .filter(pk__in=related_project_patient_ids)
                .order_by("pk")
            }
            locked_bindings = list(
                PatientAppWechatBinding.objects.select_for_update()
                .filter(
                    Q(wx_openid=wx_openid) | Q(project_patient_id__in=related_project_patient_ids)
                )
                .order_by("pk")
            )
            persistent_binding = next(
                (item for item in locked_bindings if item.wx_openid == wx_openid),
                None,
            )
            if (
                persistent_binding is not None
                and persistent_binding.project_patient_id not in locked_project_patients
            ):
                raise PatientAppBindingConflict

            active_session = None
            if active_session_ref is not None:
                active_session = (
                    PatientAppSession.objects.select_for_update()
                    .filter(
                        pk=active_session_ref.pk,
                        is_active=True,
                        expires_at__gt=now,
                    )
                    .first()
                )

            if persistent_binding is not None:
                project_patient = locked_project_patients[persistent_binding.project_patient_id]
                if (
                    active_session is not None
                    and active_session.project_patient_id == project_patient.pk
                ):
                    if active_session.wx_openid is None:
                        active_session.wx_openid = wx_openid
                        active_session.save(update_fields=["wx_openid", "updated_at"])
                    return PatientAppSessionRecovery(
                        status="authenticated",
                        token=None,
                        session=active_session,
                    )

                _lock_and_deactivate_sessions(
                    filters=Q(project_patient=project_patient) | Q(wx_openid=wx_openid),
                    now=now,
                )
                token, session = _create_patient_app_session(
                    project_patient=project_patient,
                    wx_openid=wx_openid,
                    now=now,
                )
                return PatientAppSessionRecovery(
                    status="authenticated",
                    token=token,
                    session=session,
                )

            if active_session is None:
                return PatientAppSessionRecovery(
                    status="unbound",
                    token=None,
                    session=None,
                )

            project_patient = locked_project_patients[active_session.project_patient_id]
            target_binding = next(
                (item for item in locked_bindings if item.project_patient_id == project_patient.pk),
                None,
            )
            if target_binding is not None:
                return PatientAppSessionRecovery(
                    status="unbound",
                    token=None,
                    session=None,
                )

            PatientAppWechatBinding.objects.create(
                project_patient=project_patient,
                wx_openid=wx_openid,
            )
            active_session.wx_openid = wx_openid
            active_session.save(update_fields=["wx_openid", "updated_at"])
            return PatientAppSessionRecovery(
                status="authenticated",
                token=None,
                session=active_session,
            )
    except IntegrityError as exc:
        if _is_wechat_binding_unique_conflict(exc):
            raise PatientAppBindingConflict from exc
        raise


def bind_project_patient_with_code(code: str, wx_openid: str):
    normalized_code = _normalize_binding_code(code)
    if not BINDING_CODE_PATTERN.fullmatch(normalized_code):
        raise ValidationError("绑定码无效")
    code_hash = _hash_binding_code(normalized_code)
    binding_ref = (
        PatientAppBindingCode.objects.filter(code_hash=code_hash)
        .order_by("-created_at", "-id")
        .only("id", "project_patient_id")
        .first()
    )
    if binding_ref is None:
        raise ValidationError("绑定码无效")
    related_project_patient_ids = set(
        PatientAppWechatBinding.objects.filter(
            Q(wx_openid=wx_openid) | Q(project_patient_id=binding_ref.project_patient_id)
        ).values_list("project_patient_id", flat=True)
    )
    related_project_patient_ids.add(binding_ref.project_patient_id)

    try:
        with transaction.atomic():
            locked_project_patients = {
                item.pk: item
                for item in ProjectPatient.objects.select_for_update()
                .select_related("patient")
                .filter(pk__in=related_project_patient_ids)
                .order_by("pk")
            }
            binding = (
                PatientAppBindingCode.objects.select_for_update().filter(pk=binding_ref.pk).first()
            )
            if binding is None:
                raise ValidationError("绑定码无效")
            if binding.project_patient_id not in locked_project_patients:
                raise PatientAppBindingConflict
            now = timezone.now()
            if binding.used_at is not None:
                raise ValidationError("绑定码已使用")
            if binding.revoked_at is not None:
                raise ValidationError("绑定码已撤销")
            if binding.expires_at <= now:
                raise ValidationError("绑定码已过期")

            project_patient = locked_project_patients[binding.project_patient_id]
            locked_bindings = list(
                PatientAppWechatBinding.objects.select_for_update()
                .filter(Q(wx_openid=wx_openid) | Q(project_patient=project_patient))
                .order_by("pk")
            )
            if any(
                item.project_patient_id not in locked_project_patients for item in locked_bindings
            ):
                raise PatientAppBindingConflict

            _lock_and_deactivate_sessions(
                filters=Q(project_patient_id__in=locked_project_patients),
                now=now,
            )
            if locked_bindings:
                PatientAppWechatBinding.objects.filter(
                    pk__in=[item.pk for item in locked_bindings]
                ).delete()
            PatientAppWechatBinding.objects.create(
                project_patient=project_patient,
                wx_openid=wx_openid,
            )
            token, session = _create_patient_app_session(
                project_patient=project_patient,
                wx_openid=wx_openid,
                now=now,
            )
            binding.used_at = now
            binding.save(update_fields=["used_at", "updated_at"])
    except IntegrityError as exc:
        if _is_wechat_binding_unique_conflict(exc):
            raise PatientAppBindingConflict from exc
        raise

    return token, session


def revoke_project_patient_binding(project_patient) -> None:
    now = timezone.now()
    with transaction.atomic():
        locked_project_patient = ProjectPatient.objects.select_for_update().get(
            pk=project_patient.pk
        )
        PatientAppBindingCode.objects.select_for_update().filter(
            project_patient=locked_project_patient,
            used_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=now, updated_at=now)
        PatientAppWechatBinding.objects.select_for_update().filter(
            project_patient=locked_project_patient
        ).delete()
        _lock_and_deactivate_sessions(
            filters=Q(project_patient=locked_project_patient),
            now=now,
        )
