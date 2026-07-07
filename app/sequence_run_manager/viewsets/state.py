import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_spectacular.types import OpenApiTypes
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import DatabaseError, transaction
from django.utils import timezone
from sequence_run_manager.aws_event_bridge.event_srv import emit_srsc_api_event
from sequence_run_manager.models import State, Sequence
from sequence_run_manager.serializers.state import (
    StateSerializer,
    StateCreateRequestSerializer,
    StateUpdateRequestSerializer,
)
from sequence_run_manager_proc.services.sequence_state_srv import (
    map_sequence_run_new_state_to_srsc,
)

logger = logging.getLogger(__name__)


class StateTransitionMixin:
    """
    State transition validation and side effects for manual sequence-run states.

    states_transition_validation_map structure:
    - If value is a list: ["STATE1", "STATE2"] means only these states can
      transition to the key.
    - If value is a dict with "excluded_states": all states except those listed
      can transition to the key.
    - If value is a dict with "allowed_states": same as list format.

    refer:
        "Resolved" -- https://github.com/umccr/orcabus/issues/879
    """

    states_transition_validation_map = {
        "RESOLVED": ["FAILED"],
        "DEPRECATED": ["SUCCEEDED"],
    }

    def is_valid_next_state(self, current_status, request_status: str) -> bool:
        """
        Check if transitioning from current_status to request_status is valid.
        """
        if current_status is None:
            return request_status.upper() == "DEPRECATED"

        request_status_upper = request_status.upper()
        current_status_upper = current_status.upper()

        if request_status_upper not in self.states_transition_validation_map:
            return False

        validation_rule = self.states_transition_validation_map[request_status_upper]

        if isinstance(validation_rule, dict):
            if "excluded_states" in validation_rule:
                excluded_states = [
                    state.upper() for state in validation_rule["excluded_states"]
                ]
                return current_status_upper not in excluded_states
            if "allowed_states" in validation_rule:
                allowed_states = [
                    state.upper() for state in validation_rule["allowed_states"]
                ]
                return current_status_upper in allowed_states

        if isinstance(validation_rule, list):
            allowed_states = [state.upper() for state in validation_rule]
            return current_status_upper in allowed_states

        return False

    def _validate_state_status(self, current_status, request_status):
        """Backward-compatible wrapper for the old validation method name."""
        return self.is_valid_next_state(current_status, request_status)

    def create_state_and_emit_srsc(
        self,
        sequence: Sequence,
        request_status: str,
        request_comment: str,
    ) -> tuple[State, dict]:
        """Create a manual sequence-run state and emit its SRSC event."""
        logger.info(
            "Creating manual sequence-run state: sequence_id=%s status=%s",
            sequence.orcabus_id,
            request_status,
        )
        instance = State.objects.create(
            sequence=sequence,
            status=request_status,
            timestamp=timezone.now(),
            comment=request_comment,
        )
        logger.info(
            "Manual sequence-run state persisted (pending SRSC emission): sequence_id=%s state_id=%s status=%s",
            sequence.orcabus_id,
            instance.orcabus_id,
            request_status,
        )

        if request_status in self.states_transition_validation_map:
            sequence.status = request_status
            sequence.save(update_fields=["status"])

        srsc_event = map_sequence_run_new_state_to_srsc(
            sequence,
            instance,
        ).model_dump(mode="json")
        logger.info(
            "Manual SRSC event built: sequence_id=%s state_id=%s event_id=%s status=%s",
            sequence.orcabus_id,
            instance.orcabus_id,
            srsc_event.get("id"),
            request_status,
        )

        emit_srsc_api_event(srsc_event)
        logger.info(
            "Manual SRSC event emitted: sequence_id=%s state_id=%s event_id=%s status=%s",
            sequence.orcabus_id,
            instance.orcabus_id,
            srsc_event.get("id"),
            request_status,
        )
        return instance, srsc_event


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
        description=("Update state comment only."),
    ),
)
class StateViewSet(
    StateTransitionMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    serializer_class = StateSerializer
    search_fields = State.get_base_fields()
    http_method_names = ["get", "post", "patch"]
    pagination_class = None
    lookup_value_regex = "[^/]+"  # to allow id prefix

    def get_queryset(self):
        return State.objects.filter(sequence=self.kwargs["orcabus_id"])

    @extend_schema(
        responses=OpenApiTypes.OBJECT,
        description="Get states transition validation map",
    )
    @action(
        detail=False,
        methods=["get"],
        url_name="get_states_transition_validation_map",
        url_path="get_states_transition_validation_map",
    )
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
        required_fields = {"status", "comment"}
        provided_fields = set(request.data.keys())

        if required_fields - provided_fields:
            return Response(
                {"detail": "status and comment fields are required."},
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
            if not self.is_valid_next_state(None, request_status):
                return Response(
                    {
                        "detail": "No state found for workflow run '{}'. Only DEPRECATED is allowed when there are no states.".format(
                            sequence_orcabus_id
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            latest_status = None
        else:
            latest_status = latest_state.status
            # check if the state status is valid
            if not self.is_valid_next_state(latest_status, request_status):
                return Response(
                    {
                        "detail": "Invalid state request. Can't add state '{}' to '{}'".format(
                            request_status, latest_status
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        # create state and sync sequence status atomically
        try:
            with transaction.atomic():
                instance, _ = self.create_state_and_emit_srsc(
                    sequence,
                    request_status,
                    request_comment,
                )
        except DatabaseError:
            logger.exception(
                "Manual state transition failed during database operation and was rolled back: sequence_id=%s requested_status=%s",
                sequence_orcabus_id,
                request_status,
            )
            return Response(
                {
                    "detail": "Failed to create sequence-run state. The operation was rolled back.",
                    "correlation_id": f"{sequence_orcabus_id}:{request_status}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception:
            logger.exception(
                "Manual state transition failed while constructing or emitting the SRSC event and was rolled back: sequence_id=%s requested_status=%s",
                sequence_orcabus_id,
                request_status,
            )
            return Response(
                {
                    "detail": "Failed to create sequence-run state and publish its SRSC event. The operation was rolled back.",
                    "correlation_id": f"{sequence_orcabus_id}:{request_status}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = StateSerializer(instance).data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Update a state for a sequence run.
        Currently we support "Resolved", "Deprecated"
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        required_fields = {"comment"}
        provided_fields = set(request.data.keys())

        if required_fields - provided_fields:
            return Response(
                {"detail": "comment field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = StateUpdateRequestSerializer(data=request.data, partial=partial)
        body.is_valid(raise_exception=True)
        vd = body.validated_data
        instance.comment = vd["comment"]
        instance.save(update_fields=["comment"])

        if getattr(instance, "_prefetched_objects_cache", None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        data = StateSerializer(instance).data
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_200_OK, headers=headers)
