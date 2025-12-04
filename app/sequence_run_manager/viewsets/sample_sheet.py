from sequence_run_manager.models import SampleSheet, Sequence
from sequence_run_manager.serializers.sample_sheet import SampleSheetSerializer
from rest_framework.viewsets import ViewSet
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
import hashlib
import zlib

import logging
logger = logging.getLogger(__name__)

class SampleSheetViewSet(ViewSet):
    """
    ViewSet for retrieving sample sheets nested under sequence_run
    """
    pagination_class = None
    lookup_value_regex = "[^/]+" # to allow id prefix
    lookup_field = 'orcabus_id'

    supported_checksum_types = ['md5', 'crc32', 'sha256']

    def _validate_checksum_type(self, checksum_type: str) -> bool:
        """
        Validate checksum type.
        Args:
            checksum_type: Type of checksum to validate
        Returns:
            bool: True if checksum type is valid, False otherwise
        """
        return checksum_type in self.supported_checksum_types

    def _calculate_checksum(self, sample_sheet_content_original: str, checksum_type: str = "sha256") -> str:
        """
        Calculate checksum from sample sheet content.
        Args:
            sample_sheet_content_original: Original CSV content of the sample sheet
            checksum_type: Type of checksum to calculate ('sha256', 'md5', or 'crc32')
        Returns:
            str: Checksum as hexadecimal string, or empty string if content is None/empty
        """
        if not sample_sheet_content_original:
            return ""
        try:
            content_bytes = sample_sheet_content_original.encode('utf-8')
            if checksum_type.lower() == "md5":
                return hashlib.md5(content_bytes).hexdigest()
            elif checksum_type.lower() == "crc32":
                # CRC32 returns a signed integer, convert to unsigned and then to hex
                crc32_value = zlib.crc32(content_bytes) & 0xffffffff
                return format(crc32_value, '08x')
            else:  # default to sha256
                return hashlib.sha256(content_bytes).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to calculate {checksum_type} checksum from sample sheet content: {str(e)}")
            return ""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='checksum',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Checksum value to search for',
                required=False,
            ),
            OpenApiParameter(
                name='checksumType',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Type of checksum: md5 or crc32',
                required=False,
                enum=["md5", "crc32", "sha256"],
            ),
            OpenApiParameter(
                name='sequenceRunId',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Sequence run ID to filter by (will be converted to sequence_run_id by camel-case middleware)',
                required=False,
            ),
        ],
        responses={
            200: SampleSheetSerializer(many=True),
        },
        operation_id="list_sample_sheets",
        description="List sample sheets with optional filtering by checksum and sequenceRunId"
    )
    def list(self, request, *args, **kwargs):
        """
        List sample sheets with optional filtering.

        Query parameters:
        - checksum: Checksum value to search for
        - checksumType: Type of checksum ('md5' or 'crc32')
        - sequenceRunId: Filter by sequence run ID

        Examples:
        - GET /api/v1/sample_sheet?checksum=123456789abcba987654321&checksumType=md5
        - GET /api/v1/sample_sheet?checksum=a1b2c3d4&checksumType=crc32
        - GET /api/v1/sample_sheet?sequenceRunId=sqr.123456789abcdef

        Returns a list of matching sample sheets, or empty list if no matches found.
        """
        queryset = SampleSheet.objects.filter(association_status='active')

        # Filter by sequence_run_id, checksum and checksum_type if provided
        sequence_run_id = request.query_params.get('sequence_run_id')
        checksum = request.query_params.get('checksum')
        checksum_type_param = request.query_params.get('checksum_type', 'sha256')
        checksum_type = checksum_type_param.lower() if checksum_type_param else 'sha256'

        if not (sequence_run_id or (checksum and checksum_type)):
            return Response(
                {"detail": "At least one of sequenceRunId, or  checksum and checksumType is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if checksum and checksum_type:
            if not self._validate_checksum_type(checksum_type):
                return Response(
                    {"detail": f"Invalid checksumType '{checksum_type}'. Must be one of: {', '.join(self.supported_checksum_types)}."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Filter sample sheets by matching checksum
            matching_sample_sheets = []
            for sample_sheet in queryset:
                calculated_checksum = self._calculate_checksum(
                    sample_sheet.sample_sheet_content_original or "",
                    checksum_type
                )
                if calculated_checksum.lower() == checksum.lower():
                    matching_sample_sheets.append(sample_sheet)

            queryset = matching_sample_sheets

        if sequence_run_id:
            try:
                sequence = Sequence.objects.get(sequence_run_id=sequence_run_id)
            except Sequence.DoesNotExist:
                return Response(
                    {"detail": f"Sequence run with sequence_run_id '{sequence_run_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
            queryset = queryset.filter(sequence=sequence)

        # Serialize and return results
        serializer = SampleSheetSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
        orcabus_id = kwargs.get('orcabus_id') or kwargs.get('pk')
        if not orcabus_id:
            return Response({"detail": "orcabus_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        sample_sheet = get_object_or_404(SampleSheet, orcabus_id=orcabus_id)
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
