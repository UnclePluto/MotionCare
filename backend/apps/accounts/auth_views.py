from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

# 第一版：角色到权限点映射，满足前端菜单过滤；接口级授权仍以后端为准
_ROLE_PERMISSIONS: dict[str, list[str]] = {
    User.Role.SUPER_ADMIN: [
        "patient.read",
        "patient.write",
        "project.read",
        "project.write",
        "randomization.confirm",
        "visit.write",
        "prescription.write",
        "prescription.terminate",
        "training.write",
        "health.write",
        "crf.read",
        "crf.export",
        "user.manage",
    ],
    User.Role.ADMIN: [
        "patient.read",
        "patient.write",
        "project.read",
        "project.write",
        "randomization.confirm",
        "visit.write",
        "prescription.write",
        "prescription.terminate",
        "training.write",
        "health.write",
        "crf.read",
        "crf.export",
        "user.manage",
    ],
    User.Role.DOCTOR: [
        "patient.read",
        "patient.write",
        "project.read",
        "project.write",
        "randomization.confirm",
        "visit.write",
        "prescription.write",
        "prescription.terminate",
        "training.write",
        "health.write",
        "crf.read",
        "crf.export",
        "user.manage",
    ],
}


def _permissions_for_role(role: str) -> list[str]:
    return list(_ROLE_PERMISSIONS.get(role, _ROLE_PERMISSIONS[User.Role.DOCTOR]))


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfCookieView(APIView):
    """GET：写入 csrftoken Cookie，供后续 POST 使用。"""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    def get(self, request):
        return Response({"detail": "ok"})


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    def post(self, request):
        phone = (request.data.get("phone") or request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not phone:
            return Response({"code": "AUTH_INVALID", "message": "请填写手机号"}, status=400)
        user = authenticate(request, phone=phone, password=password)
        if user is None:
            return Response({"code": "AUTH_INVALID", "message": "手机号或密码错误"}, status=401)
        if not user.is_active:
            return Response({"code": "AUTH_DISABLED", "message": "账号已停用"}, status=403)
        login(request, user)
        return Response(status=204)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.id,
                "phone": user.phone,
                "name": user.name,
                "gender": user.gender,
                "role": user.role,
                "roles": [user.role],
                "permissions": _permissions_for_role(user.role),
                "must_change_password": user.must_change_password,
            }
        )
