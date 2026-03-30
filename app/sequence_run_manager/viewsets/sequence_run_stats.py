from django.db import models
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.serializers.sequence_run import (
    SequenceRunCountByStatusSerializer,
    SequenceRunListParamSerializer,
)


class SequenceStatsViewSet(GenericViewSet):
    """
    ViewSet for sequence-related statistics.
    """

    def get_queryset(self):
        """
        Build sequence queryset using sequence-run list semantics:
        - keyword filters via `Sequence.objects.get_by_keyword`
        - optional time filters via sequence `start_time`/`end_time`
        - optional `library_id` filter
        - fake sequence runs are excluded (`status__isnull=False`)
        """
        start_time = self.request.query_params.get("start_time", "")
        end_time = self.request.query_params.get("end_time", "")

        library_id = self.request.query_params.get("library_id", "")

        # Custom query params that are not direct Sequence fields for get_by_keyword.
        exclude_keys = {
            "start_time",
            "end_time",
            "search",
            "order_by",
            "library_id",
        }
        keyword_params = {
            key: value
            for key, value in self.request.query_params.items()
            if key not in exclude_keys
        }

        result_set = (
            Sequence.objects.get_by_keyword(**keyword_params)
            .distinct()
            .filter(status__isnull=False)  # filter out fake sequence runs
        )

        if library_id:
            sequence_ids = (
                LibraryAssociation.objects.filter(library_id=library_id)
                .values_list("sequence_id", flat=True)
            )
            result_set = result_set.filter(orcabus_id__in=sequence_ids)

        if start_time and end_time:
            result_set = result_set.filter(
                Q(start_time__range=[start_time, end_time])
                | Q(end_time__range=[start_time, end_time])
            )

        return result_set

    @extend_schema(
        parameters=[SequenceRunListParamSerializer],
        responses=SequenceRunCountByStatusSerializer,
    )
    @action(detail=False, methods=["GET"])
    def status_counts(self, request):
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
