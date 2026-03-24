from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_spectacular.types import OpenApiTypes
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from sequence_run_manager.models import State, Sequence
from sequence_run_manager.serializers.state import StateSerializer, StateCreateRequestSerializer, StateUpdateRequestSerializer

@extend_schema_view(
    create=extend_schema(
        request=StateCreateRequestSerializer,
        responses={201: StateSerializer},
        description=(
            "Create a state (body: status, comment; JSON uses camelCase per API settings)."
        ),
    ),
    partial_update=extend_schema(
        request=StateUpdateRequestSerializer,
        responses={200: StateSerializer},
        description=(
            "Update state comment only."
        ),
    )
)
class StateViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin,  GenericViewSet):
    serializer_class = StateSerializer
    search_fields = State.get_base_fields()
    http_method_names = ['get', 'post', 'patch']
    pagination_class = None
    lookup_value_regex = "[^/]+" # to allow id prefix

    """
    states_transition_validation_map for state creation, update
    refer:
        "Resolved" -- https://github.com/umccr/orcabus/issues/879
    """
    states_transition_validation_map = {
        'RESOLVED': ['FAILED'],
        'DEPRECATED': ['SUCCEEDED']
    }

    def get_queryset(self):
        return State.objects.filter(sequence=self.kwargs["orcabus_id"])

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Get states transition validation map")
    @action(detail=False, methods=['get'], url_name='get_states_transition_validation_map', url_path='get_states_transition_validation_map')
    def get_states_transition_validation_map(self, request, **kwargs):
        """
        Returns states transition validation map.
        """
        return Response(self.states_transition_validation_map)

    def create(self, request, *args, **kwargs):
        """
        Create a customed new state for a sequence run.
        Currently we support "Resolved"
        """
        allowed_fields = {"status", "comment"}
        required_fields = {"status", "comment"}
        provided_fields = set(request.data.keys())

        if required_fields - provided_fields:
            return Response(
                {"detail": "status and comment fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if provided_fields - allowed_fields:
            return Response(
                {"detail": "Only status and comment fields are allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sequence_orcabus_id = self.kwargs.get("orcabus_id")
        sequence = Sequence.objects.get(orcabus_id=sequence_orcabus_id)

        body = StateCreateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        vd = body.validated_data
        request_status = vd["status"].upper()
        request_comment = vd["comment"]

        latest_state = sequence.get_latest_state()
        # Handle case when there's no latest state - only allow DEPRECATED
        if not latest_state:
            if request_status != 'DEPRECATED':
                return Response({"detail": "No state found for workflow run '{}'. Only DEPRECATED is allowed when there are no states.".format(wfr_orcabus_id)},
                                status=status.HTTP_400_BAD_REQUEST)
            latest_status = None
        else:
            latest_status = latest_state.status
            # check if the state status is valid
            if not self._validate_state_status(latest_status, request_status):
                return Response({"detail": "Invalid state request. Can't add state '{}' to '{}'".format(request_status, latest_status)},
                                status=status.HTTP_400_BAD_REQUEST)

        instance = State.objects.create(
            sequence=sequence,
            status=request_status,
            timestamp=timezone.now(),
            comment=request_comment,
        )

        data = StateSerializer(instance).data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


    def update(self, request, *args, **kwargs):
        """
        Update a state for a sequence run.
        Currently we support "Resolved", "Deprecated"
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        allowed_fields = {"comment"}
        required_fields = {"comment"}
        provided_fields = set(request.data.keys())

        if required_fields - provided_fields:
            return Response(
                {"detail": "comment field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if provided_fields - allowed_fields:
            return Response(
                {"detail": "Only comment field can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = StateUpdateRequestSerializer(data=request.data, partial=partial)
        body.is_valid(raise_exception=True)
        vd = body.validated_data
        instance.comment = vd["comment"]
        instance.save(update_fields=["comment"])

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        data = StateSerializer(instance).data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_200_OK, headers=headers)

    def _validate_state_status(self, current_status, request_status):
        """
        check if the state status is valid:
        states_transition_validation_map[request_state] in current_state.status
        """
        if request_status not in self.states_transition_validation_map:
            return False
        if current_status not in self.states_transition_validation_map[request_status]:
            return False
        return True
