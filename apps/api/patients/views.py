from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Patient


@require_GET
def list_patients(request):
    if not request.user.is_authenticated:
        return JsonResponse({"code": "AUTH_REQUIRED", "message": "未登录"}, status=401)

    items = [{"id": p.id, "name": p.name, "phone": p.phone} for p in Patient.objects.all()]
    return JsonResponse({"items": items})

