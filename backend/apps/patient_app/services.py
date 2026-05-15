import re
import secrets

from django.core.exceptions import ValidationError
from django.core.signing import salted_hmac
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.patient_app.models import PatientAppBindingCode, PatientAppSession
from apps.studies.models import ProjectPatient

BINDING_CODE_ALPHABET = "0123456789"
BINDING_CODE_LENGTH = 4
BINDING_CODE_MAX_ATTEMPTS = 20
BINDING_CODE_TTL = timezone.timedelta(minutes=15)
BINDING_CODE_PATTERN = re.compile(r"^[0-9]{4}$")
SESSION_TTL = timezone.timedelta(days=30)


def _normalize_binding_code(code: str) -> str:
    return code if isinstance(code, str) else ""


def _hash_binding_code(code: str) -> str:
    return salted_hmac("patient_app.binding_code", _normalize_binding_code(code)).hexdigest()


def hash_patient_app_token(token: str) -> str:
    return salted_hmac("patient_app.session_token", token).hexdigest()


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
            active_collision_exists = PatientAppBindingCode.objects.select_for_update().filter(
                code_hash=code_hash,
                used_at__isnull=True,
                revoked_at__isnull=True,
            ).exists()
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


def bind_project_patient_with_code(code: str, wx_openid: str):
    now = timezone.now()
    normalized_code = _normalize_binding_code(code)
    if not BINDING_CODE_PATTERN.fullmatch(normalized_code):
        raise ValidationError("绑定码无效")
    code_hash = _hash_binding_code(normalized_code)

    with transaction.atomic():
        binding_ref = (
            PatientAppBindingCode.objects.filter(code_hash=code_hash)
            .order_by("-created_at", "-id")
            .only("id", "project_patient_id")
            .first()
        )
        if binding_ref is None:
            raise ValidationError("绑定码无效")
        ProjectPatient.objects.select_for_update().get(pk=binding_ref.project_patient_id)
        binding = (
            PatientAppBindingCode.objects.select_for_update()
            .select_related("project_patient__patient")
            .filter(pk=binding_ref.pk)
            .first()
        )
        if binding is None:
            raise ValidationError("绑定码无效")
        if binding.used_at is not None:
            raise ValidationError("绑定码已使用")
        if binding.revoked_at is not None:
            raise ValidationError("绑定码已撤销")
        if binding.expires_at <= now:
            raise ValidationError("绑定码已过期")

        project_patient = binding.project_patient
        PatientAppSession.objects.select_for_update().filter(
            project_patient=project_patient,
            is_active=True,
        ).update(is_active=False, updated_at=now)

        token = secrets.token_urlsafe(32)
        session = PatientAppSession.objects.create(
            project_patient=project_patient,
            patient=project_patient.patient,
            wx_openid=wx_openid,
            token_hash=hash_patient_app_token(token),
            expires_at=now + SESSION_TTL,
        )
        binding.used_at = now
        binding.save(update_fields=["used_at", "updated_at"])

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
        PatientAppSession.objects.select_for_update().filter(
            project_patient=locked_project_patient,
            is_active=True,
        ).update(is_active=False, updated_at=now)
