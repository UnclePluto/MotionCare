from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import User
from .serializers import ChangePasswordSerializer, UserSerializer


class UserViewSet(ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = User.objects.order_by("-date_joined", "-id")
        if self.action == "list":
            return qs.filter(role=User.Role.DOCTOR)
        return qs

    @action(detail=False, methods=["post"], url_path="me/change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])
        return Response({"detail": "密码已修改"})
