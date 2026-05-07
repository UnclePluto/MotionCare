from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST


@ensure_csrf_cookie
@require_GET
def csrf(_request):
    return JsonResponse({"ok": True})


@require_POST
def login_view(request):
    user = authenticate(
        request,
        username=request.POST.get("username", ""),
        password=request.POST.get("password", ""),
    )
    if user is None:
        return JsonResponse({"code": "AUTH_INVALID", "message": "用户名或密码错误"}, status=401)
    login(request, user)
    return JsonResponse({}, status=204)


@require_GET
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"code": "AUTH_REQUIRED", "message": "未登录"}, status=401)

    roles = ["doctor"]
    permissions = ["patient.read", "patient.write", "project.read", "project.write"]
    return JsonResponse({"username": request.user.username, "roles": roles, "permissions": permissions})

