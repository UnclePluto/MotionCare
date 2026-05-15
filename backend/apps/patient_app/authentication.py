from dataclasses import dataclass

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.patient_app.models import PatientAppSession
from apps.patient_app.services import hash_patient_app_token


@dataclass(frozen=True)
class PatientAppPrincipal:
    session: PatientAppSession

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def project_patient(self):
        return self.session.project_patient

    @property
    def patient(self):
        return self.session.patient


class PatientAppTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw_header = get_authorization_header(request).decode("utf-8")
        if not raw_header:
            return None

        parts = raw_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
            raise AuthenticationFailed("患者端认证格式错误")

        token_hash = hash_patient_app_token(parts[1])
        session = (
            PatientAppSession.objects.select_related(
                "project_patient",
                "project_patient__project",
                "project_patient__patient",
                "patient",
            )
            .filter(
                token_hash=token_hash,
                is_active=True,
                expires_at__gt=timezone.now(),
            )
            .first()
        )
        if session is None:
            raise AuthenticationFailed("患者端登录已失效")

        session.last_seen_at = timezone.now()
        session.save(update_fields=["last_seen_at", "updated_at"])
        principal = PatientAppPrincipal(session=session)
        return principal, session
