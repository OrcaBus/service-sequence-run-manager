from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework import filters
from rest_framework.settings import api_settings

from sequence_run_manager.pagination import StandardResultsSetPagination
from django.shortcuts import get_object_or_404

from sequence_run_manager.models import Sequence
from sequence_run_manager.serializers.sequence_run import SequenceRunSerializer, SequenceRunListParamSerializer, SequenceRunMinSerializer, SequenceRunGroupByInstrumentRunIdSerializer
from sequence_run_manager.serializers.sample_sheet import SampleSheetSerializer
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.viewsets.base import BaseViewSet
from sequence_run_manager.viewsets.utils import (
    filtered_sequence_runs_queryset,
    instrument_run_groups_queryset,
)

# Allowed ordering fields for ongoing/unresolved actions (with optional - prefix)
ALLOWED_ORDER_FIELDS = frozenset([
    'orcabus_id', '-orcabus_id', 'instrument_run_id', '-instrument_run_id',
    'start_time', '-start_time', 'end_time', '-end_time',
    'status', '-status',
])


class SequenceRunViewSet(BaseViewSet):
    serializer_class = SequenceRunSerializer
    search_fields = Sequence.get_base_fields()
    # Search is applied in ``get_queryset`` via ``sequence_run_manager.viewsets.utils.filtered_sequence_runs_queryset`` (same
    # text match as stats / ``list_by_instrument_run_id``). Omit ``SearchFilter`` to avoid
    # double-filtering on the same ``search`` query param.
    filter_backends = [filters.OrderingFilter]
    queryset = Sequence.objects.all()
    lookup_value_regex = "[^/]+" # to allow id prefix
    lookup_field = 'orcabus_id'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._has_custom_ordering = False

    @staticmethod
    def _validate_ordering(ordering: str | None) -> str | None:
        """Return a safe ordering value, or None if missing / not in the allow-list."""
        if not ordering or not isinstance(ordering, str):
            return None
        s = ordering.strip()
        if not s or s not in ALLOWED_ORDER_FIELDS:
            return None
        return s


    def filter_queryset(self, queryset):
        """
        Override to prevent OrderingFilter from applying default ordering
        when we have a custom order_by parameter.
        """
        # Check if we have custom ordering (stored in instance variable from get_queryset)
        if self._has_custom_ordering:
            # We have custom ordering, so we need to prevent OrderingFilter from applying default ordering
            # Temporarily store original filter_backends
            original_backends = self.filter_backends
            # Filter out OrderingFilter by checking the class type
            self.filter_backends = [f for f in self.filter_backends if f != filters.OrderingFilter]
            try:
                # Apply filters without OrderingFilter
                queryset = super().filter_queryset(queryset)
            finally:
                # Restore original filter_backends
                self.filter_backends = original_backends
        else:
            # No custom ordering, use default behavior
            queryset = super().filter_queryset(queryset)

        return queryset

    def get_queryset(self):
        """
        Same shared filters as ``list_by_instrument_run_id`` and ``stats/sequence_run_status_counts`` (see
        ``sequence_run_manager.viewsets.utils.filtered_sequence_runs_queryset``). The ``status``
        query param filters ``Sequence.status`` on each row. Optional ``order_by`` / ``ordering``
        when the value is in the allow-list.
        """
        raw_order = (
            self.request.query_params.get("order_by")
            or self.request.query_params.get(api_settings.ORDERING_PARAM)
            or ""
        ).strip()
        order_by = self._validate_ordering(raw_order)
        self._has_custom_ordering = order_by is not None

        result_set = filtered_sequence_runs_queryset(
            self.request.query_params,
            apply_sequence_status_param=True,
        )
        if order_by:
            result_set = result_set.order_by(order_by)

        return result_set.distinct()

    @extend_schema(responses={200: SequenceRunSerializer, 404: OpenApiResponse(description="Sequence run not found.")}, operation_id="get_sequence_run_by_orcabus_id")
    def retrieve(self, request, *args, **kwargs):
        """
        Returns a single Sequence record by its orcabus_id.
        GET /api/v1/sequence_run/{orcabus_id}/
        """
        orcabus_id = kwargs.get('orcabus_id') or kwargs.get('pk')
        if not orcabus_id:
            return Response({"detail": "orcabus_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        sequence = get_object_or_404(Sequence, orcabus_id=orcabus_id)
        return Response(SequenceRunSerializer(sequence).data, status=status.HTTP_200_OK)

    @extend_schema(
        parameters=[
            SequenceRunListParamSerializer
        ],
        responses={
            200: SequenceRunMinSerializer(many=True)
        }
    )
    def list(self, request, *args, **kwargs):
        self.serializer_class = SequenceRunMinSerializer
        return super().list(request, *args, **kwargs)

    @extend_schema(
        parameters=[
            SequenceRunListParamSerializer
        ],
        responses={
            200: SequenceRunGroupByInstrumentRunIdSerializer(many=True)
        }
    )

    @action(detail=False, methods=["get"], url_name="list_by_instrument_run_id", url_path="list_by_instrument_run_id")
    def list_by_instrument_run_id(self, request, *args, **kwargs):
        """
        Group sequences by instrument_run_id and return with items array.
        The ``status`` query param filters by the **group** status: the ``status`` of the latest
        sequence in the group (by ``start_time``, then ``orcabus_id``), not each row's field alone.
        Other params match the list endpoint (see ``filtered_sequence_runs_queryset``).
        """
        raw_order = (
            self.request.query_params.get("order_by")
            or self.request.query_params.get(api_settings.ORDERING_PARAM)
            or ""
        ).strip()
        order_by = self._validate_ordering(raw_order)

        sequence_set = filtered_sequence_runs_queryset(
            self.request.query_params,
            apply_sequence_status_param=False,
        )
        if order_by:
            sequence_set = sequence_set.order_by(order_by)

        grouped_data = instrument_run_groups_queryset(sequence_set)
        status_filter = self.request.query_params.get("status", "").strip()
        if status_filter:
            grouped_data = grouped_data.filter(group_status=status_filter)

        paginator = StandardResultsSetPagination()
        paginated_groups = paginator.paginate_queryset(grouped_data, request)

        result = []
        for group in paginated_groups:
            instrument_run_id = group["instrument_run_id"]
            if not instrument_run_id:
                continue
            sequences = sequence_set.filter(instrument_run_id=instrument_run_id).order_by("start_time")
            sequence_status = group.get("group_status")
            sequence_items = SequenceRunMinSerializer(sequences, many=True).data

            result.append(
                {
                    "instrument_run_id": instrument_run_id,
                    "start_time": group["start_time"],
                    "end_time": group["end_time"],
                    "count": group["count"],
                    "status": sequence_status,
                    "items": sequence_items,
                }
            )

        return paginator.get_paginated_response(result)

    @extend_schema(
        responses={
            200: SampleSheetSerializer,
            404: OpenApiResponse(description="No sample sheet found for this sequence matching the sample_sheet_name.")
        },
        operation_id="get_sequence_sample_sheet"
    )
    @action(detail=True, methods=["get"], url_name="sample_sheet", url_path="sample_sheet")
    def sample_sheet(self, request, *args, **kwargs):
        """
        Returns a single SampleSheet record for a sequence that matches the sequence's sample_sheet_name.
        If there are multiple sample sheets with the same name, returns the latest one (by association_timestamp).
        GET /api/v1/sequence_run/{orcabus_id}/sample_sheet/
        """
        orcabus_id = kwargs.get('orcabus_id') or kwargs.get('pk')
        if not orcabus_id:
            return Response({"detail": "orcabus_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        sequence_run = get_object_or_404(Sequence, orcabus_id=orcabus_id)
        if not sequence_run.sample_sheet_name:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            sample_sheet = (
                SampleSheet.objects
                .filter(
                    sequence=sequence_run,
                    sample_sheet_name=sequence_run.sample_sheet_name,
                    association_status='active'
                )
                .order_by('-association_timestamp')
                .first()
            )
            if not sample_sheet:
                raise SampleSheet.DoesNotExist()
        except SampleSheet.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(SampleSheetSerializer(sample_sheet).data, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: SampleSheetSerializer,
            404: OpenApiResponse(description="No sample sheet found with the given orcabus_id for this sequence.")
        },
        operation_id="get_sequence_sample_sheet_by_orcabus_id"
    )
    @action(detail=True, methods=["get"], url_name="sample_sheet_by_orcabus_id", url_path="sample_sheet/(?P<ss_orcabus_id>[^/]+)")
    def sample_sheet_by_orcabus_id(self, request, *args, **kwargs):
        """
        Returns a single SampleSheet record by its orcabus_id for a specific sequence.
        GET /api/v1/sequence_run/{orcabus_id}/sample_sheet/{ss_orcabus_id}/
        """
        sequence_run = get_object_or_404(Sequence, orcabus_id=kwargs.get('orcabus_id'))
        sample_sheet = get_object_or_404(SampleSheet, orcabus_id=kwargs.get('ss_orcabus_id'), sequence=sequence_run)
        return Response(SampleSheetSerializer(sample_sheet).data, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: SampleSheetSerializer(many=True),
            404: OpenApiResponse(description="No sample sheets found for this sequence.")
        },
        operation_id="get_sequence_sample_sheets"
    )
    @action(detail=True, methods=["get"], url_name="sample_sheets", url_path="sample_sheets")
    def sample_sheets(self, request, *args, **kwargs):
        """
        Returns all SampleSheet records for a sequence.
        GET /api/v1/sequence_run/{orcabus_id}/sample_sheets/
        """
        orcabus_id = kwargs.get('orcabus_id') or kwargs.get('pk')
        if not orcabus_id:
            return Response({"detail": "orcabus_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        sequence = get_object_or_404(Sequence, orcabus_id=orcabus_id)
        sample_sheets = SampleSheet.objects.filter(sequence=sequence, association_status='active')
        if not sample_sheets.exists():
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(SampleSheetSerializer(sample_sheets, many=True).data, status=status.HTTP_200_OK)
