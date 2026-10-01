from sequence_run_manager.models import State
from sequence_run_manager.serializers.base import (
    SerializersBase,
    OrcabusIdListField,
    OrcabusIdSerializerMetaMixin,
)
from rest_framework import serializers


class StateBaseSerializer(SerializersBase):
    # Authorship is derived from the caller's Bearer JWT, never from the body.
    created_by = serializers.CharField(read_only=True, allow_null=True)


class StateSerializer(StateBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = State
        fields = "__all__"


class StateUpdateRequestSerializer(serializers.Serializer):
    """
    Schema contract for PATCH /state/{id}.
    Request accepts only `comment`.
    """

    comment = serializers.CharField(required=True, allow_blank=False)


class StateTransitionRequestSerializer(serializers.Serializer):
    """
    Schema contract for POST /sequence_run/state/{transition}/.
    The endpoint determines the target state. The request body contains
    sequenceRunOrcabusIds (list or CSV string) and comment.
    """

    sequence_run_orcabus_ids = OrcabusIdListField(
        child=serializers.CharField(allow_blank=False),
        required=True,
        allow_empty=False,
    )
    comment = serializers.CharField(required=True, allow_blank=False)


class StateTransitionValidationErrorSerializer(serializers.Serializer):
    """Field-level validation errors returned for an invalid transition request."""

    sequence_run_orcabus_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    comment = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    non_field_errors = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )


class StateTransitionFailureSerializer(serializers.Serializer):
    sequence_run_orcabus_id = serializers.CharField()
    reason = serializers.CharField()
    detail = serializers.CharField()


class StateTransitionResponseSerializer(serializers.Serializer):
    """
    Schema contract for sequence-run state transition responses.
    JSON responses use camelCase (createdCount, sequenceRunOrcabusIds, failedCount).
    """

    created_count = serializers.IntegerField()
    sequence_run_orcabus_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )
    failed_count = serializers.IntegerField(default=0)
    failures = StateTransitionFailureSerializer(
        many=True,
        required=False,
    )
