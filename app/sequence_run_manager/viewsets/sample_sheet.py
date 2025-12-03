from sequence_run_manager.models import SampleSheet, Sequence
from sequence_run_manager.serializers.sample_sheet import SampleSheetSerializer
from rest_framework.viewsets import ViewSet
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiResponse
import hashlib

import logging
logger = logging.getLogger(__name__)

class SampleSheetViewSet(ViewSet):
    """
    ViewSet for retrieving sample sheet by its orcabus_id or checksum
    """
    pagination_class = None
    lookup_value_regex = "[^/]+" # to allow id prefix
    lookup_field = 'orcabus_id'

    def _calculate_checksum(self, sample_sheet_content_original: str) -> str:
        """
        Calculate SHA256 checksum from sample sheet content.

        Args:
            sample_sheet_content_original: Original CSV content of the sample sheet

        Returns:
            str: SHA256 checksum as hexadecimal string, or empty string if content is None/empty
        """
        if not sample_sheet_content_original:
            return ""
        try:
            return hashlib.sha256(sample_sheet_content_original.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to calculate checksum from sample sheet content: {str(e)}")
            return ""

    def get_object(self):
        """
        Override to use orcabus_id from URL kwargs (pk from router)
        """
        orcabus_id = self.kwargs.get('pk') or self.kwargs.get('orcabus_id')
        return get_object_or_404(SampleSheet, orcabus_id=orcabus_id)

    @extend_schema(
        responses={
            200: SampleSheetSerializer,
            404: OpenApiResponse(description="Sample sheet not found.")
        },
        operation_id="get_sample_sheet_by_id"
    )
    def retrieve(self, request, *args, **kwargs):
        """
        Returns a SampleSheet by its orcabus_id.
        GET /api/v1/sample_sheet/{orcabus_id}
        """
        sample_sheet = self.get_object()
        return Response(SampleSheetSerializer(sample_sheet).data, status=status.HTTP_200_OK)

    @extend_schema(
        responses={
            200: SampleSheetSerializer,
            404: OpenApiResponse(description="Sample sheet not found or checksum does not match.")
        },
        operation_id="verify_sample_sheet_checksum",
        description="Verifies that a sample sheet's checksum matches the provided checksum. The checksum is calculated from the sample_sheet_content_original field using SHA256. This allows clients to verify sample sheet integrity."
    )
    @action(detail=True, methods=["get"], url_name="checksum", url_path="checksum/(?P<checksum>[^/]+)")
    def checksum(self, request, *args, **kwargs):
        """
        Verifies that a sample sheet's checksum matches the provided checksum.
        GET /api/v1/sample_sheet/{orcabus_id}/checksum/{checksum}

        The checksum is calculated from the sample_sheet_content_original field using SHA256.
        This allows clients to verify sample sheet integrity by comparing the provided checksum
        with the calculated checksum of the sample sheet with the given orcabus_id.
        """
        # Get the sample sheet by orcabus_id
        sample_sheet = self.get_object()

        # Get the checksum from URL parameters
        provided_checksum = kwargs.get('checksum')
        if not provided_checksum:
            return Response(
                {"detail": "Checksum parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate the checksum for this sample sheet
        calculated_checksum = self._calculate_checksum(sample_sheet.sample_sheet_content_original or "")

        # Verify the checksums match
        if calculated_checksum != provided_checksum:
            return Response(
                {
                    "status": "mismatch",
                    "message": f"Checksum mismatch. Provided checksum: {provided_checksum}. Calculated checksum: {calculated_checksum}",
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Checksums match, return the sample sheet
        return Response({"status": "match", "message": "Checksum matches."}, status=status.HTTP_200_OK)


class SampleSheetBySequenceRunViewSet(ViewSet):
    """
    ViewSet for sample sheet actions on sequence runs
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
