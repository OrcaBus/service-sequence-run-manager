from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework import filters
from rest_framework.settings import api_settings
from sequence_run_manager.viewsets.base import BaseViewSet
from sequence_run_manager.pagination import StandardResultsSetPagination
from django.db.models import Q, Count, Min, Max
from sequence_run_manager.models import Sequence, LibraryAssociation
from sequence_run_manager.serializers.sequence_run import SequenceRunSerializer, SequenceRunListParamSerializer, SequenceRunMinSerializer, SequenceRunGroupByInstrumentRunIdSerializer
from sequence_run_manager.serializers.sample_sheet import SampleSheetSerializer
from sequence_run_manager.models.sample_sheet import SampleSheet
from django.shortcuts import get_object_or_404


class SequenceRunViewSet(BaseViewSet):
    serializer_class = SequenceRunSerializer
    search_fields = Sequence.get_base_fields()
    queryset = Sequence.objects.all()
    lookup_value_regex = "[^/]+" # to allow id prefix
    lookup_field = 'orcabus_id'

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

        # Extract search term before excluding params
        search_term = self.request.query_params.get(api_settings.SEARCH_PARAM)

        # exclude the custom query params from the rest of the query params
        def exclude_params(params):
            for param in params:
                self.request.query_params.pop(param) if param in self.request.query_params.keys() else None

        exclude_params([
            'start_time',
            'end_time',
        ])

        # Get all sequences using get_by_keyword (this excludes search param internally)
        sequence_set = Sequence.objects.get_by_keyword(**self.request.query_params).distinct()

        # Manually apply search filter if search parameter is provided (This is needed because custom actions don't go through DRF's filter_backends)
        if search_term and self.search_fields:
            search_filter = filters.SearchFilter()
            search_filter.search_fields = self.search_fields
            sequence_set = search_filter.filter_queryset(self.request, sequence_set, self)

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
                sequence_status = sequences.filter(status__isnull=False).order_by('start_time').last().status

                # Convert sequences to list of dictionaries manually
                sequence_items = SequenceRunMinSerializer(sequences, many=True).data

                result.append({
                    'instrument_run_id': instrument_run_id,
                    'start_time': group['start_time'],
                    'end_time': group['end_time'],
                    'count': group['count'],
                    'status': sequence_status,
                    'items': sequence_items
                })

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
