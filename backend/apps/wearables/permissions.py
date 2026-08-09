from apps.accounts.models import User
from apps.studies.models import ProjectPatient


def manageable_project_patients(user):
    queryset = ProjectPatient.objects.select_related("patient", "project", "group")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if user.role not in {User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.DOCTOR}:
        return queryset.none()
    return queryset
