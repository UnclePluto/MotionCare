import re

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.miniapp_signed_assets import build_signed_static_asset_manifest
from apps.common.miniapp_static_asset_registry import REGISTERED_STATIC_ASSET_MANIFESTS

from .throttles import MiniappStaticAssetRateThrottle


class StaticAssetManifestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [MiniappStaticAssetRateThrottle]
    http_method_names = ["get"]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def handle_exception(self, exc):
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        return Response(
            {"detail": "训练素材暂时不可用，请稍后重试"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def get(self, request):
        if set(request.query_params) != {"version"}:
            return Response({"detail": "请求参数无效"}, status=status.HTTP_400_BAD_REQUEST)

        versions = request.query_params.getlist("version")
        if len(versions) != 1 or re.fullmatch(r"v-[a-f0-9]{12}", versions[0]) is None:
            return Response({"detail": "请求参数无效"}, status=status.HTTP_400_BAD_REQUEST)

        version = versions[0]
        if version not in REGISTERED_STATIC_ASSET_MANIFESTS:
            return Response({"detail": "素材版本不存在"}, status=status.HTTP_404_NOT_FOUND)

        try:
            manifest = build_signed_static_asset_manifest(version)
        except Exception:
            return Response(
                {"detail": "训练素材暂时不可用，请稍后重试"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(manifest)
