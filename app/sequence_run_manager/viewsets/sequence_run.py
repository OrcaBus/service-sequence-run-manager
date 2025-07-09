from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from sequence_run_manager.viewsets.base import BaseViewSet
from sequence_run_manager.pagination import StandardResultsSetPagination
from django.db.models import Q, Count, Min, Max
from sequence_run_manager.models import Sequence, LibraryAssociation
from sequence_run_manager.serializers.sequence_run import SequenceRunSerializer, SequenceRunListParamSerializer, SequenceRunMinSerializer, SequenceRunGroupByInstrumentRunIdSerializer


class SequenceRunViewSet(BaseViewSet):
    serializer_class = SequenceRunSerializer
    search_fields = Sequence.get_base_fields()
    queryset = Sequence.objects.all()
    lookup_value_regex = "[^/]+" # to allow id prefix

    def get_queryset(self):
        """
        custom query params:
        start_time: start time of the sequence run
        end_time: end time of the sequence run

        library_id: library id of the sequence run
        """

        start_time = self.request.query_params.get('start_time', 0)
        end_time = self.request.query_params.get('end_time', 0)
        library_id = self.request.query_params.get('library_id', 0)

        # exclude the custom query params from the rest of the query params
        def exclude_params(params):
            for param in params:
                self.request.query_params.pop(param) if param in self.request.query_params.keys() else None

        exclude_params([
            'start_time',
            'end_time',
            'library_id',
        ])
        result_set = Sequence.objects.get_by_keyword(**self.request.query_params).distinct().filter(status__isnull=False) # filter out fake sequence runs

        if start_time and end_time:
            result_set = result_set.filter(Q(start_time__range=[start_time, end_time]) | Q(end_time__range=[start_time, end_time]))
        if library_id:
            sequence_ids = LibraryAssociation.objects.filter(library_id=library_id).values_list('sequence_id', flat=True)
            result_set = result_set.filter(orcabus_id__in=sequence_ids)

        return result_set.distinct()


    @extend_schema(parameters=[
        SequenceRunListParamSerializer
    ])
    def list(self, request, *args, **kwargs):
        self.serializer_class = SequenceRunMinSerializer
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=[
        SequenceRunListParamSerializer
    ],
    responses={
        200: StandardResultsSetPagination().get_paginated_response_schema(SequenceRunGroupByInstrumentRunIdSerializer().get_schema())}
    )

    @action(detail=False, methods=["get"], url_name="list_by_instrument_run_id", url_path="list_by_instrument_run_id")
    def list_by_instrument_run_id(self, request, *args, **kwargs):
        """
        Group sequences by instrument_run_id and return with items array
        custom query params:
        start_time: start time of the sequence run
        end_time: end time of the sequence run
        library_id: library id of the sequence run
        page: page number for pagination
        rows_per_page: number of items per page
        """
        start_time = self.request.query_params.get('start_time', 0)
        end_time = self.request.query_params.get('end_time', 0)

        # exclude the custom query params from the rest of the query params
        def exclude_params(params):
            for param in params:
                self.request.query_params.pop(param) if param in self.request.query_params.keys() else None

        exclude_params([
            'start_time',
            'end_time',
        ])

        # Get all sequences
        sequence_set = Sequence.objects.get_by_keyword(**self.request.query_params).distinct()

        # Apply time filters if provided
        if start_time and end_time:
            sequence_set = sequence_set.filter(Q(start_time__range=[start_time, end_time]) | Q(end_time__range=[start_time, end_time]))

        # Group by instrument_run_id and get aggregated data
        grouped_data = sequence_set.values('instrument_run_id').annotate(
            count=Count('instrument_run_id'),
            start_time=Min('start_time'),
            end_time=Max('end_time')
        ).distinct().order_by('-start_time')

        # Apply pagination to the grouped QuerySet first
        paginator = StandardResultsSetPagination()
        paginated_groups = paginator.paginate_queryset(grouped_data, request)

        # Build the response with items array for the paginated groups
        result = []
        for group in paginated_groups:
            instrument_run_id = group['instrument_run_id']
            if instrument_run_id:  # Only include if instrument_run_id is not None
                # Get all sequences for this instrument_run_id
                sequences = sequence_set.filter(instrument_run_id=instrument_run_id).order_by('start_time')

                # Convert sequences to list of dictionaries manually
                sequence_items = SequenceRunMinSerializer(sequences, many=True).data

                result.append({
                    'instrument_run_id': instrument_run_id,
                    'start_time': group['start_time'],
                    'end_time': group['end_time'],
                    'count': group['count'],
                    'items': sequence_items
                })

        return paginator.get_paginated_response(result)
