from sequence_run_manager.models import SampleSheet, Sequence
from sequence_run_manager.serializers.sample_sheet import SampleSheetSerializer
from rest_framework.viewsets import ViewSet
from rest_framework import mixins
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiResponse

import logging
logger = logging.getLogger(__name__)

class SampleSheetViewSet(ViewSet):
    """
    ViewSet for sample sheet
    """
    queryset = Sequence.objects.all()
    pagination_class = None
    lookup_value_regex = "[^/]+" # to allow id prefix

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
        Returns all active SampleSheet records for a sequence.
        """
        # pk is the orcabus_id since it's the primary key
        sequence = get_object_or_404(Sequence, orcabus_id=kwargs.get('pk'))
        sample_sheets = SampleSheet.objects.filter(sequence=sequence, association_status='active')
        if not sample_sheets.exists():
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(SampleSheetSerializer(sample_sheets, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: SampleSheetSerializer,
            404: OpenApiResponse(description="No active sample sheet found for this sequence.")
        },
        operation_id="get_sequence_sample_sheet"
    )
    @action(detail=True, methods=["get"], url_name="sample_sheet", url_path="sample_sheet")
    def sample_sheet(self, request, *args, **kwargs):
        """
        Returns a single active SampleSheet record for a sequence that matches the sequence's sample_sheet_name.
        """
        # pk is the orcabus_id since it's the primary key
        sequence_run = get_object_or_404(Sequence, orcabus_id=kwargs.get('pk'))
        if not sequence_run.sample_sheet_name:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            sample_sheet = (
                SampleSheet.objects
                .filter(
                    sequence=sequence_run,
                    association_status='active',
                    sample_sheet_name=sequence_run.sample_sheet_name
                )
                .order_by('-association_timestamp')
                .first()
            )
            if not sample_sheet:
                raise SampleSheet.DoesNotExist()
        except SampleSheet.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(SampleSheetSerializer(sample_sheet).data, status=status.HTTP_200_OK)
