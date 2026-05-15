from rest_framework.permissions import BasePermission


PASSWORD_CHANGE_ALLOWED_PATHS = {
    "/api/me/",
    "/api/auth/logout/",
    "/api/accounts/users/me/change-password/",
}


def is_password_change_allowed_path(path: str) -> bool:
    normalized = path if path.endswith("/") else f"{path}/"
    return normalized in PASSWORD_CHANGE_ALLOWED_PATHS


def passes_password_change_gate(request) -> bool:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "must_change_password", False) and not is_password_change_allowed_path(request.path):
        return False
    return True


class IsAuthenticatedAndPasswordChanged(BasePermission):
    message = "请先修改默认密码"

    def has_permission(self, request, view):
        return passes_password_change_gate(request)


class IsAdminOrDoctor(BasePermission):
    message = "请先修改默认密码"

    def has_permission(self, request, view):
        return bool(
            passes_password_change_gate(request)
            and request.user.role in {"super_admin", "admin", "doctor"}
        )
