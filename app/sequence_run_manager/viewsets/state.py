import logging
from functools import partial

from drf_spectacular.utils import (
    OpenApiResponse,
    PolymorphicProxySerializer,
    extend_schema,
    extend_schema_view,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import DatabaseError, transaction
from django.utils import timezone
from sequence_run_manager.aws_event_bridge.event_srv import emit_srsc_api_event
from sequence_run_manager.models import State, Sequence
from sequence_run_manager.serializers.state import (
    StateSerializer,
    StateUpdateRequestSerializer,
    StateTransitionRequestSerializer,
    StateTransitionResponseSerializer,
    StateTransitionValidationErrorSerializer,
)
from sequence_run_manager.viewsets.utils import get_email_from_bearer_authorization
from sequence_run_manager_proc.services.sequence_state_srv import (
    map_sequence_run_new_state_to_srsc,
    srsc_event_detail,
)

logger = logging.getLogger(__name__)


STATE_TRANSITION_RESPONSES = {
    status.HTTP_201_CREATED: OpenApiResponse(
        response=StateTransitionResponseSerializer,
        description="Every requested sequence run was transitioned successfully.",
    ),
    status.HTTP_207_MULTI_STATUS: OpenApiResponse(
        response=StateTransitionResponseSerializer,
        description="Some sequence runs were transitioned and some failed.",
    ),
    status.HTTP_400_BAD_REQUEST: OpenApiResponse(
        response=PolymorphicProxySerializer(
            component_name="SequenceRunStateTransitionBadRequest",
            serializers=[
                StateTransitionValidationErrorSerializer,
                StateTransitionResponseSerializer,
            ],
            resource_type_field_name=None,
        ),
        description=(
            "The request body failed serializer validation, or every requested "
            "transition failed because a sequence run was not found or the "
            "transition was invalid."
        ),
    ),
    status.HTTP_401_UNAUTHORIZED: OpenApiResponse(
        description="A valid Bearer JWT with an email claim is required.",
    ),
    status.HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(
        response=StateTransitionResponseSerializer,
        description=(
            "No requested transition succeeded, and at least one failed during "
            "state creation."
        ),
    ),
}


class InvalidStateTransition(ValueError):
    """Raised when locked transition validation rejects a requested state."""


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
        "Deprecated" -- https://github.com/OrcaBus/service-sequence-run-manager/issues/19
    """

    states_transition_validation_map = {
        "RESOLVED": ["FAILED"],
        "DEPRECATED": ["SUCCEEDED"],
    }

    @staticmethod
    def normalize_sequence_run_orcabus_id(orcabus_id: str) -> str:
        if orcabus_id.startswith("seq."):
            return orcabus_id[4:]
        return orcabus_id

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

    def create_state_and_build_srsc(
        self,
        sequence: Sequence,
        request_status: str,
        request_comment: str,
        created_by: str,
    ) -> tuple[State, dict]:
        """Create a manual sequence-run state and build its SRSC event.

        `created_by` is the normalized email from the caller's Bearer JWT; it is
        the sole source of authorship, never the request body.
        """
        logger.info(
            "Creating manual sequence-run state: sequence_id=%s status=%s created_by=%s",
            sequence.orcabus_id,
            request_status,
            created_by,
        )
        instance = State.objects.create(
            sequence=sequence,
            status=request_status,
            timestamp=timezone.now(),
            comment=request_comment,
            created_by=created_by,
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

        srsc_event = srsc_event_detail(
            map_sequence_run_new_state_to_srsc(
                sequence,
                instance,
            )
        )
        logger.info(
            "Manual SRSC event built: sequence_id=%s state_id=%s event_id=%s status=%s",
            sequence.orcabus_id,
            instance.orcabus_id,
            srsc_event.get("id"),
            request_status,
        )

        return instance, srsc_event

    def publish_srsc_after_commit(
        self,
        *,
        srsc_event: dict,
        sequence_id: str,
        state_id: str,
        request_status: str,
    ) -> None:
        """Publish a committed transition, logging enough context for recovery."""
        try:
            emit_srsc_api_event(srsc_event)
        except Exception:
            # Publication is best-effort until a transactional outbox is added.
            # Keep this message queryable so CloudWatch can alarm on it and the
            # event can be reconstructed from sequence_id/state_id.
            logger.exception(
                "Manual SRSC publication failed after database commit: "
                "sequence_id=%s state_id=%s event_id=%s status=%s "
                "recoverable=true",
                sequence_id,
                state_id,
                srsc_event.get("id"),
                request_status,
            )
            return

        logger.info(
            "Manual SRSC event emitted after database commit: "
            "sequence_id=%s state_id=%s event_id=%s status=%s",
            sequence_id,
            state_id,
            srsc_event.get("id"),
            request_status,
        )

    @staticmethod
    def _failure_response_status(failures: list[dict]) -> int:
        """Choose the most helpful HTTP status when no transition succeeds.

        - All client-side reasons (NOT_FOUND, INVALID_TRANSITION) -> 400
        - Anything else (state creation failed) -> 500

        SRSC emission happens after the database commit, so an emission failure
        cannot fail a transition; it is logged as recoverable instead.
        """
        client_failure_reasons = {"NOT_FOUND", "INVALID_TRANSITION"}
        reasons = {failure.get("reason") for failure in failures}
        if reasons <= client_failure_reasons:
            return status.HTTP_400_BAD_REQUEST
        return status.HTTP_500_INTERNAL_SERVER_ERROR


@extend_schema_view(
    partial_update=extend_schema(
        request=StateUpdateRequestSerializer,
        responses={
            200: StateSerializer,
            401: OpenApiResponse(
                description="A valid Bearer JWT with an email claim is required."
            ),
            403: OpenApiResponse(
                description="The authenticated user did not create this state."
            ),
        },
        description=(
            "Update the state comment only. Bearer authentication is required; "
            "only custom states (RESOLVED, DEPRECATED) are editable, and states "
            "with a recorded creator may only be updated by that creator."
        ),
    ),
)
class StateViewSet(
    StateTransitionMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    get_success_headers = mixins.CreateModelMixin.get_success_headers
    serializer_class = StateSerializer
    search_fields = State.get_base_fields()
    http_method_names = ["get", "patch"]
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

    def update(self, request, *args, **kwargs):
        """
        Update the comment of a custom state ("Resolved", "Deprecated").

        Requires a Bearer JWT; when the state records a creator, only that
        creator may edit it. States created before creator auditing have no
        recorded creator and stay editable by any authenticated caller.
        """
        partial = kwargs.pop("partial", False)
        actor = get_email_from_bearer_authorization(request)
        instance = self.get_object()

        required_fields = {"comment"}
        provided_fields = set(request.data.keys())

        if required_fields - provided_fields:
            return Response(
                {"detail": "comment field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only user-created states carry an editable comment; system states
        # (STARTED, SUCCEEDED, ...) are not in the transition map.
        if instance.status not in self.states_transition_validation_map:
            return Response(
                {"detail": "Invalid state status to update comment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        creator = (instance.created_by or "").strip().lower()
        if creator and creator != actor:
            logger.warning(
                "State comment update rejected for non-creator: state_id=%s actor=%s creator=%s",
                instance.orcabus_id,
                actor,
                creator,
            )
            raise PermissionDenied(
                "You don't have permission to update this state comment."
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


class SequenceRunStateTransitionViewSet(StateTransitionMixin, GenericViewSet):
    """User-initiated sequence run state transitions for one or more runs."""

    http_method_names = ["get", "post"]
    pagination_class = None

    @extend_schema(
        # Distinct from the same map served under
        # /sequence_run/{orcabusId}/state/, which otherwise collides on operationId.
        operation_id="apiV1SequenceRunStateTransitionValidationMapRetrieve",
        responses=OpenApiTypes.OBJECT,
        description="Get states transition validation map.",
    )
    @action(
        detail=False,
        methods=["get"],
        url_name="get_states_transition_validation_map",
        url_path="get_states_transition_validation_map",
    )
    def get_states_transition_validation_map(self, request, **kwargs):
        """Return the state transition validation map."""
        return Response(self.states_transition_validation_map)

    def _transition_one(
        self,
        sequence: Sequence,
        normalized_id: str,
        request_status: str,
        request_comment: str,
        created_by: str,
    ) -> State:
        """Transition a single sequence run under a row lock.

        The Sequence row is the shared lock target for every state transition,
        including sequences that do not have State rows. ``sequence.status`` read
        before the lock is compared with the locked value so a concurrent update
        is visible in the logs.

        Raises:
            InvalidStateTransition: The locked status does not allow request_status.
        """
        observed_status = sequence.status

        with transaction.atomic():
            locked_sequence = Sequence.objects.select_for_update().get(
                orcabus_id=normalized_id
            )
            current_status = locked_sequence.status

            if current_status != observed_status:
                logger.warning(
                    "Sequence status changed before transition lock was acquired: "
                    "sequence_id=%s requested_status=%s observed_status=%s "
                    "locked_status=%s concurrent_update=true",
                    sequence.orcabus_id,
                    request_status,
                    observed_status,
                    current_status,
                )

            if not self.is_valid_next_state(current_status, request_status):
                logger.warning(
                    "Manual state transition rejected after locked validation: "
                    "sequence_id=%s requested_status=%s current_status=%s",
                    sequence.orcabus_id,
                    request_status,
                    current_status,
                )
                if current_status is None:
                    raise InvalidStateTransition(
                        "No current state found for sequence run '{}'. Only "
                        "DEPRECATED is allowed when there is no current state.".format(
                            sequence.orcabus_id
                        )
                    )
                raise InvalidStateTransition(
                    "Invalid state request. Can't add state '{}' to sequence run '{}' from '{}'".format(
                        request_status,
                        sequence.orcabus_id,
                        current_status,
                    )
                )

            instance, srsc_event = self.create_state_and_build_srsc(
                locked_sequence,
                request_status,
                request_comment,
                created_by,
            )
            transaction.on_commit(
                partial(
                    self.publish_srsc_after_commit,
                    srsc_event=srsc_event,
                    sequence_id=str(locked_sequence.orcabus_id),
                    state_id=str(instance.orcabus_id),
                    request_status=request_status,
                ),
                robust=True,
            )

        return instance

    def _state_transition(self, request, request_status: str):
        # Authenticate before touching the body: authorship comes from the JWT
        # only, and a missing or malformed token fails the whole request (401).
        created_by = get_email_from_bearer_authorization(request)
        body = StateTransitionRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        vd = body.validated_data

        sequence_run_orcabus_ids = vd["sequence_run_orcabus_ids"]
        request_comment = vd["comment"]

        normalized_ids = [
            self.normalize_sequence_run_orcabus_id(orcabus_id)
            for orcabus_id in sequence_run_orcabus_ids
        ]
        sequences = list(Sequence.objects.filter(orcabus_id__in=normalized_ids))
        sequences_by_normalized_id = {
            self.normalize_sequence_run_orcabus_id(sequence.orcabus_id): sequence
            for sequence in sequences
        }

        created_sequence_run_ids = []
        failures = []

        for raw_id, normalized_id in zip(sequence_run_orcabus_ids, normalized_ids):
            sequence = sequences_by_normalized_id.get(normalized_id)
            if not sequence:
                logger.warning(
                    "Manual state transition skipped missing sequence run: sequence_id=%s requested_status=%s",
                    raw_id,
                    request_status,
                )
                failures.append(
                    {
                        "sequence_run_orcabus_id": raw_id,
                        "reason": "NOT_FOUND",
                        "detail": "Sequence run not found.",
                    }
                )
                continue

            try:
                state_instance = self._transition_one(
                    sequence,
                    normalized_id,
                    request_status,
                    request_comment,
                    created_by,
                )
            except InvalidStateTransition as exc:
                failures.append(
                    {
                        "sequence_run_orcabus_id": sequence.orcabus_id,
                        "reason": "INVALID_TRANSITION",
                        "detail": str(exc),
                    }
                )
                continue
            except DatabaseError:
                logger.exception(
                    "Manual state transition failed during database operation and was rolled back: "
                    "sequence_id=%s requested_status=%s",
                    sequence.orcabus_id,
                    request_status,
                )
                failures.append(
                    {
                        "sequence_run_orcabus_id": sequence.orcabus_id,
                        "reason": "STATE_CREATION_FAILED",
                        "detail": "Failed to create sequence-run state. The operation was rolled back.",
                    }
                )
                continue
            except Exception:
                logger.exception(
                    "Manual state transition failed before commit and was rolled back: "
                    "sequence_id=%s requested_status=%s",
                    sequence.orcabus_id,
                    request_status,
                )
                failures.append(
                    {
                        "sequence_run_orcabus_id": sequence.orcabus_id,
                        "reason": "STATE_CREATION_FAILED",
                        "detail": "Failed to create sequence-run state. The operation was rolled back.",
                    }
                )
                continue

            created_sequence_run_ids.append(sequence.orcabus_id)
            logger.info(
                "Manual state transition completed: sequence_id=%s state_id=%s status=%s",
                sequence.orcabus_id,
                state_instance.orcabus_id,
                request_status,
            )

        response_status = status.HTTP_201_CREATED
        if failures:
            response_status = (
                status.HTTP_207_MULTI_STATUS
                if created_sequence_run_ids
                else self._failure_response_status(failures)
            )

        summary = StateTransitionResponseSerializer(
            instance={
                "created_count": len(created_sequence_run_ids),
                "sequence_run_orcabus_ids": created_sequence_run_ids,
                "failed_count": len(failures),
                "failures": failures,
            }
        )
        logger.info(
            "Manual state transition finished: requested_status=%s created_count=%s failed_count=%s response_status=%s",
            request_status,
            len(created_sequence_run_ids),
            len(failures),
            response_status,
        )
        return Response(summary.data, status=response_status)

    @extend_schema(
        request=StateTransitionRequestSerializer,
        responses=STATE_TRANSITION_RESPONSES,
        summary="Mark sequence runs as deprecated",
        description=(
            "Transition sequence runs from SUCCEEDED to DEPRECATED, record the "
            "Bearer JWT email as the state creator, and emit an SRSC event for "
            "each transitioned run once the transaction commits."
        ),
    )
    @action(detail=False, methods=["post"], url_path="deprecate")
    def deprecate(self, request, *args, **kwargs):
        return self._state_transition(request, "DEPRECATED")

    @extend_schema(
        request=StateTransitionRequestSerializer,
        responses=STATE_TRANSITION_RESPONSES,
        summary="Mark sequence runs as resolved",
        description=(
            "Transition sequence runs from FAILED to RESOLVED, record the Bearer "
            "JWT email as the state creator, and emit an SRSC event for each "
            "transitioned run once the transaction commits."
        ),
    )
    @action(detail=False, methods=["post"], url_path="resolve")
    def resolve(self, request, *args, **kwargs):
        return self._state_transition(request, "RESOLVED")
