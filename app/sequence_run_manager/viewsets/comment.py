from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema, extend_schema_view
from sequence_run_manager.models.comment import Comment, TargetType
from sequence_run_manager.models.sequence import Sequence
from sequence_run_manager.serializers.comment import CommentSerializer, CommentCreateRequestSerializer, CommentUpdateRequestSerializer
from sequence_run_manager.viewsets.base import get_email_from_bearer_authorization


@extend_schema_view(
    create=extend_schema(
        request=CommentCreateRequestSerializer,
        responses={201: CommentSerializer},
        description=(
            "Create a comment (body: `comment`, `created_by`). "
        ),
    ),
    partial_update=extend_schema(
        request=CommentUpdateRequestSerializer,
        responses={200: CommentSerializer},
        description=(
            "Update comment text. Authorization is derived from `Authorization: Bearer <jwt>` (email claim "
            "must match the comment's original `created_by`). Request accepts `comment` and optional "
            "`created_by` (empty allowed; ignored for the update)."
        ),
    ),
    destroy=extend_schema(
        request=None,
        responses={204: None},
        description="Soft-delete. Caller must present Authorization: Bearer <jwt> (RS256); email claim must match comment author (created_by). Signature is not verified here — authenticate at API Gateway.",
    ),
)
class CommentViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, GenericViewSet):
    serializer_class = CommentSerializer
    search_fields = Comment.get_base_fields()
    pagination_class = None
    lookup_value_regex = "[^/]+" # to allow id prefix
    # PatchOnlyViewSet excludes PUT; we extend it with DELETE for soft-delete.
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Comment.objects.filter(
            target_id=self.kwargs["orcabus_id"],
            is_deleted=False
        )

    def perform_create(self, serializer):
        serializer.save(target_id=self.kwargs["orcabus_id"])

    def create(self, request, *args, **kwargs):
        seq_orcabus_id = self.kwargs["orcabus_id"]

        # Check if the SequenceRun exists
        try:
            Sequence.objects.get(orcabus_id=seq_orcabus_id)
        except Sequence.DoesNotExist:
            return Response({"detail": "SequenceRun not found."}, status=status.HTTP_404_NOT_FOUND)

        # Validate input payload shape: only `comment` + `created_by`
        input_serializer = CommentCreateRequestSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        comment_obj = Comment.objects.create(
            target_id=seq_orcabus_id,
            target_type=TargetType.SEQUENCE,
            **input_serializer.validated_data,
        )
        serializer = self.get_serializer(comment_obj)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object() # PATCH always calls this with partial=True; we don't use it.

        body = CommentUpdateRequestSerializer(data=request.data, partial=partial)
        body.is_valid(raise_exception=True)
        vd = body.validated_data

        if "created_by" in vd and vd["created_by"] is not None and vd["created_by"] != "":
            actor = vd["created_by"].strip().lower()
        else:
            actor = get_email_from_bearer_authorization(request)
        author = (instance.created_by or "").strip().lower()
        if author != actor:
            raise PermissionDenied("You don't have permission to update this comment.")

        instance.comment = vd["comment"]
        instance.save(update_fields=["comment", "updated_at"])

        data = CommentSerializer(instance).data # return the updated comment
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_200_OK, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        email = get_email_from_bearer_authorization(request)
        author = (instance.created_by or "").strip().lower()
        if email != author:
            raise PermissionDenied("You don't have permission to delete this comment.")

        # Soft-delete only flips is_deleted; severity (and text) stay for audit/UI history.
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
