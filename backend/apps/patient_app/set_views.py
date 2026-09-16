from rest_framework import serializers
from rest_framework.response import Response

from apps.training.sets import (
    open_session,
    owned_session,
    serialize_session,
    update_set,
    recover_session,
)
from .views import PatientAppBaseView
from .serializers import ClientOffsetDateTimeField


class OpenSessionSerializer(serializers.Serializer):
    client_session_id = serializers.UUIDField()
    prescription_action = serializers.IntegerField(min_value=1)
    started_at = ClientOffsetDateTimeField()


class SetOperationSerializer(serializers.Serializer):
    operation = serializers.ChoiceField(choices=["start", "complete", "abandon"])
    attempt_id = serializers.UUIDField()
    started_at = ClientOffsetDateTimeField(required=False)
    ended_at = ClientOffsetDateTimeField(required=False)


class MotionSessionView(PatientAppBaseView):
    def post(self, request):
        data = OpenSessionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        session, created = open_session(self.project_patient(), **data.validated_data)
        return Response(serialize_session(session), status=201 if created else 200)


class MotionSessionDetailView(PatientAppBaseView):
    def get(self, request, session_id):
        return Response(serialize_session(owned_session(self.project_patient(), session_id)))


class MotionSetView(PatientAppBaseView):
    def post(self, request, session_id, index):
        data = SetOperationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        session = update_set(self.project_patient(), session_id, index, **data.validated_data)
        return Response(serialize_session(session))


class CompletedSetSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=1)
    attempt_id = serializers.UUIDField()
    started_at = ClientOffsetDateTimeField()
    ended_at = ClientOffsetDateTimeField()


class RecoverSessionSerializer(OpenSessionSerializer):
    completed_sets = CompletedSetSerializer(many=True, allow_empty=False)


class MotionSessionRecoverView(PatientAppBaseView):
    def post(self, request):
        data = RecoverSessionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        session = recover_session(self.project_patient(), **data.validated_data)
        return Response(serialize_session(session))
