from sequence_run_manager.models import Comment
from sequence_run_manager.serializers.base import SerializersBase, OrcabusIdSerializerMetaMixin
from rest_framework import serializers

class CommentBaseSerializer(SerializersBase):
    pass


class CommentSerializer(CommentBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = Comment
        fields = "__all__"

class CommentCreateRequestSerializer(serializers.Serializer):
    comment = serializers.CharField(required=True, allow_blank=False)
    created_by = serializers.CharField(required=True, allow_blank=False, max_length=255)

class CommentUpdateRequestSerializer(serializers.Serializer):
    comment = serializers.CharField(required=True, allow_blank=False)
    # `created_by` is optional and may be empty; PATCH authorization is derived from the bearer token email claim.
    created_by = serializers.CharField(required=False, allow_blank=True, max_length=255)
