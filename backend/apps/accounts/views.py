from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import User
from .serializers import ChangePasswordSerializer, UserSerializer


class UserViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrDoctor]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = User.objects.order_by("-date_joined", "-id")
        if self.action == "list":
            return qs.filter(role=User.Role.DOCTOR)
        return qs.filter(Q(role=User.Role.DOCTOR) | Q(pk=self.request.user.pk))

    @action(detail=False, methods=["post"], url_path="me/change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])
        update_session_auth_hash(request, request.user)
        return Response({"detail": "密码已修改"})
