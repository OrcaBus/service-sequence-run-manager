import base64
import gzip
import ulid
from typing import Optional
from django.utils import timezone
import logging
from rest_framework import status
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, OpenApiResponse

from sequence_run_manager.models import Sequence, SampleSheet, LibraryAssociation, Comment
from sequence_run_manager.models.comment import TargetType
from sequence_run_manager.aws_event_bridge.event_srv import emit_srm_api_event

from v2_samplesheet_parser.functions.parser import parse_samplesheet


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ASSOCIATION_STATUS = "ACTIVE"

class SequenceRunActionViewSet(ViewSet):
    """
    ViewSet for sequence run actions

    add_samplesheet:
        upload sample sheet for a sequence run
    """

    @extend_schema(
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'The sample sheet file to upload'
                    },
                    'instrument_run_id': {
                        'type': 'string',
                        'description': 'The instrument run ID to associate with the sample sheet'
                    },
                    'created_by': {
                        'type': 'string',
                        'description': 'The user who is creating this sample sheet'
                    },
                    'comment': {
                        'type': 'string',
                        'description': 'Comment about the sample sheet'
                    }
                },
                'required': ['file', 'instrument_run_id', 'created_by', 'comment']
            }
        },
        responses={
            200: OpenApiResponse(description="Sample sheet added successfully"),
            400: OpenApiResponse(description="Missing required fields or invalid input"),
            500: OpenApiResponse(description="Internal server error")
        },
        description="Creating a fake sequence run and associate a samplesheet to it by emitting an SRSSC and/or SRLLC event to EventBridge (Orcabus)",
        tags=["Sequence Run Actions"]
    )
    @action(detail=False,methods=['post'],url_name='add_samplesheet',url_path='add_samplesheet')
    def add_samplesheet(self, request, *args, **kwargs):
        """
        upload sample sheet for a sequence run
        """
        # get uploaded samplesheet
        uploaded_samplesheet = request.FILES.get('file')
        if not uploaded_samplesheet:
            return Response({"detail": "No samplesheet uploaded"}, status=status.HTTP_400_BAD_REQUEST)
        samplesheet_name = uploaded_samplesheet.name
        instrument_run_id = request.POST.get('instrument_run_id')
        if not instrument_run_id:
            return Response({"detail": "instrument_run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        created_by = request.POST.get('created_by')
        if not created_by:
            return Response({"detail": "created_by is required"}, status=status.HTTP_400_BAD_REQUEST)
        comment = request.POST.get('comment')
        if not comment:
            return Response({"detail": "comment is required"}, status=status.HTTP_400_BAD_REQUEST)

        # step 1: create a fake sequence run
        sequence_run = Sequence.objects.create(
            instrument_run_id=instrument_run_id,
            sequence_run_id="r."+ulid.new().str,
            sample_sheet_name=samplesheet_name,
            start_time=timezone.now()  # add start time to record the time when the (ghost) sequence run is created
        )
        logger.info(f"Sequence run created for instrument run {instrument_run_id}")

        # step 2: read the uploaded samplesheet, and encodeed with base64
        samplesheet_content = ''
        with uploaded_samplesheet.open('rb') as f:
            samplesheet_content = f.read()

        # Decode bytes to string for parsing
        samplesheet_content_str = samplesheet_content.decode('utf-8')

        try:
            samplesheet_content_json = parse_samplesheet(samplesheet_content_str)
        except Exception as e:
            logger.error(f"Failed to parse samplesheet: {e}")
            return Response({"detail": f"Invalid samplesheet format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # step 3: save samplesheet to database
        sample_sheet = SampleSheet.objects.create(
            sequence=sequence_run,
            sample_sheet_name=samplesheet_name,
            sample_sheet_content=samplesheet_content_json,
        )

        comment_obj = Comment.objects.create(
            target_id=sample_sheet.orcabus_id,
            target_type=TargetType.SAMPLE_SHEET,
            comment=comment,
            created_by=created_by,
        )
        logger.info(f"Samplesheet saved for sequence run {sequence_run.sequence_run_id}, and comment {comment_obj.orcabus_id} saved")

        # step 4: construct event bridge detail and emit event to event bridge
        samplesheet_base64_gz = base64.b64encode(gzip.compress(samplesheet_content)).decode('utf-8')
        samplesheet_change_eb_payload = construct_samplesheet_change_eb_payload(sequence_run, samplesheet_base64_gz, sample_sheet, comment_obj)

        try:
            emit_srm_api_event(samplesheet_change_eb_payload)
            logger.info(f"Samplesheet change event emitted for sequence run {sequence_run.sequence_run_id}")
        except Exception as e:
            logger.error(f"Failed to emit samplesheet change event: {e}")
            # Continue processing even if event emission fails

        # step 5: check if there is library linking change, if there is any change, create library associations and emit event to event bridge
        linking_libraries = list(dict.fromkeys(entry["sample_id"] for entry in samplesheet_content_json.get("bclconvert_data", [])))
        if linking_libraries:
            existing_libraries = LibraryAssociation.objects.filter(sequence=sequence_run).values_list('library_id', flat=True)

            if not existing_libraries or set(existing_libraries) != set(linking_libraries):
                # step 6: create library associations if there is any change
                if not existing_libraries:
                    logger.info(f"No library associations found for sequence run {sequence_run.sequence_run_id}, linked libraries: {linking_libraries}")
                else:
                    LibraryAssociation.objects.filter(sequence=sequence_run).delete()
                    logger.info(f"Library associations deleted for sequence run {sequence_run.sequence_run_id}, linked libraries: {linking_libraries}")

                for library_id in linking_libraries:
                    LibraryAssociation.objects.create(
                        sequence=sequence_run,
                        library_id=library_id,
                        association_date=timezone.now(),  # Use timezone-aware datetime
                        status=ASSOCIATION_STATUS,
                    )
                logger.info(f"Library associations created for sequence run {sequence_run.sequence_run_id}, linked libraries: {linking_libraries}")

                # step 7: emit library linking change event to event bridge
                library_linking_change_eb_payload = construct_library_linking_change_eb_payload(sequence_run, linking_libraries)
                try:
                    emit_srm_api_event(library_linking_change_eb_payload)
                    logger.info(f"Library linking change event emitted for sequence run {sequence_run.sequence_run_id}")
                except Exception as e:
                    logger.error(f"Failed to emit library linking change event: {e}")
                    # Continue processing even if event emission fails

            else:
                logger.info(f"Library associations already exist for sequence run {sequence_run.sequence_run_id}, linked libraries: {linking_libraries}")

        else:
            logger.info(f"No library linking found in samplesheet for sequence run {sequence_run.sequence_run_id}")

        return Response({"detail": "Samplesheet added successfully"}, status=status.HTTP_200_OK)


def construct_samplesheet_change_eb_payload(sequence_run: Sequence, samplesheet_base64_gz: str, sample_sheet: SampleSheet, comment: Optional[Comment]) -> dict:
    """
    Construct event bridge detail for samplesheet change based on the sequence run, sample sheet and comment
    """
    return {
        "eventType": "SequenceRunSampleSheetChange",
        "instrumentRunId": sequence_run.instrument_run_id,
        "sequenceRunId": sequence_run.sequence_run_id,
        "sampleSheet": sample_sheet,
        "samplesheetBase64gz": samplesheet_base64_gz,
        "comment":comment
    }


def construct_library_linking_change_eb_payload(sequence_run: Sequence, linked_libraries: list) -> dict:
    """
    Construct event bridge detail for library linking change based on the sequence run and linked libraries
    """
    return {
        "eventType": "SequenceRunLibraryLinkingChange",
        "instrumentRunId": sequence_run.instrument_run_id,
        "sequenceRunId": sequence_run.sequence_run_id,
        "timeStamp": timezone.now(),
        "linkedLibraries": linked_libraries,
    }
