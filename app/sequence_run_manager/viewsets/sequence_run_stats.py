from django.db import models
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from sequence_run_manager.viewsets.utils import (
    filtered_sequence_runs_queryset,
    instrument_run_groups_queryset,
)
from sequence_run_manager.serializers.sequence_run import (
    SequenceRunCountByStatusSerializer,
    SequenceRunListQueryParamSerializer,
)


class SequenceStatsViewSet(GenericViewSet):
    """
    Sequence-run statistics at ``GET /api/v1/stats/sequence_run_status_counts/`` and
    ``GET /api/v1/stats/instrument_run_status_counts/`` (same filter query params as list endpoints).
    """

    def get_queryset(self):
        """
        Filters for **per-sequence** ``sequence_run_status_counts``: same as ``GET /sequence_run/`` —
        ``status`` applies to ``Sequence.status`` on each row (see
        ``filtered_sequence_runs_queryset`` with default ``apply_sequence_status_param``).
        """
        return filtered_sequence_runs_queryset(
            self.request.query_params,
            apply_sequence_status_param=True,
        )

    @extend_schema(
        parameters=[SequenceRunListQueryParamSerializer],
        responses=SequenceRunCountByStatusSerializer,
        operation_id="stats_sequence_run_status_counts",
    )
    @action(detail=False, methods=["GET"], url_path="sequence_run_status_counts")
    def sequence_run_status_counts(self, request):
        queryset = self.get_queryset()
        status_counts = queryset.values("status").annotate(count=models.Count("status"))

        counts = {
            "all": queryset.count(),
            "started": 0,
            "succeeded": 0,
            "failed": 0,
            "aborted": 0,
            "resolved": 0,
            "deprecated": 0,
        }

        for item in status_counts:
            if item["status"] is not None:
                key = item["status"].lower()
                if key in counts:
                    counts[key] = item["count"]

        return Response(
            counts,
            status=200,
        )

    @extend_schema(
        parameters=[SequenceRunListQueryParamSerializer],
        responses=SequenceRunCountByStatusSerializer,
        operation_id="stats_instrument_run_status_counts",
    )
    @action(detail=False, methods=["GET"], url_path="instrument_run_status_counts")
    def instrument_run_status_counts(self, request):
        """
        Counts by **instrument-run group** status (same definition as
        ``list_by_instrument_run_id`` ``status`` field): latest non-null ``Sequence.status``
        within each ``instrument_run_id``. Query params match the grouped list except
        ``status`` filters groups by that computed value. ``all`` is the number of groups.
        """
        sequence_set = filtered_sequence_runs_queryset(
            request.query_params,
            apply_sequence_status_param=False,
        )
        grouped = instrument_run_groups_queryset(sequence_set)
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            grouped = grouped.filter(group_status=status_filter)

        counts = {
            "all": grouped.count(),
            "started": 0,
            "succeeded": 0,
            "failed": 0,
            "aborted": 0,
            "resolved": 0,
            "deprecated": 0,
        }

        # Count distinct instrument runs per group_status. Without ``distinct=True``, a second
        # ``values().annotate`` can join ``Sequence`` again and count one row per *sequence*,
        # inflating e.g. SUCCEEDED when one instrument run has several sequence rows.
        per_status = grouped.values("group_status").annotate(
            count=models.Count("instrument_run_id", distinct=True)
        )
        for item in per_status:
            if item["group_status"] is not None:
                key = item["group_status"].lower()
                if key in counts:
                    counts[key] = item["count"]

        return Response(counts, status=200)
