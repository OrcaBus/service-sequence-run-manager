from django.db import transaction
from django.utils import timezone
import logging
import base64

from sequence_run_manager.models.sequence import Sequence
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment
from sequence_run_manager_proc.services.bssh_srv import BSSHService

from v2_samplesheet_parser.functions.parser import parse_samplesheet

logger = logging.getLogger(__name__)

def create_sequence_sample_sheet_from_bssh_event(payload: dict):
    """
    Check if the sample sheet for a sequence exists;
    if not, create it
    """
    assert payload["id"] is not None, "sequence run id is required"

    sequence_run = Sequence.objects.get(sequence_run_id=payload["id"])
    if not sequence_run:
        logger.error(f"Sequence run {payload['id']} not found when checking or creating sequence sample sheet")
        raise ValueError(f"Sequence run {payload['id']} not found")

    return create_sequence_sample_sheet(sequence_run, payload)

def create_sequence_sample_sheet_from_srssc_event(event_detail: dict):
    """
    Check or create sequence sample sheet from event detail
    """

    assert event_detail["id"] is not None, "sequence run id is required"
    assert event_detail["sampleSheetName"] is not None, "sample sheet name is required"
    assert event_detail["samplesheetbase64gz"] is not None, "sample sheet base64 is required"
    assert event_detail["comment"] is not None, "comment is required"

    sequence_run = Sequence.objects.get(sequence_run_id=event_detail["id"])
    if not sequence_run:
        logger.error(f"Sequence run {event_detail['id']} not found when checking or creating sequence sample sheet from event")
        raise ValueError(f"Sequence run {event_detail['id']} not found")


    content_base64 = event_detail["samplesheetbase64gz"]
    content_dict = parse_samplesheet(base64.b64decode(content_base64))

    sample_sheet = SampleSheet.objects.create(
        sequence=sequence_run,
        sample_sheet_name=event_detail["sampleSheetName"],
        sample_sheet_content=content_dict,
    )

    # comment object needed for sample sheet, refer: https://github.com/umccr/orcabus/issues/947
    # create a comment for the sample sheet
    Comment.objects.create(
        association_id=sample_sheet.orcabus_id,
        comment=event_detail["comment"]["comment"],
        created_by=event_detail["comment"]["created_by"],
    )


@transaction.atomic
def create_sequence_sample_sheet(sequence: Sequence, payload: dict  ):
    """
    Create a sample sheet for a sequence
    """
    # sample_sheet_name = payload.get("sampleSheetName")

    api_url = payload.get("apiUrl")

    bssh_srv = BSSHService()
    # sample_sheet_content = bssh_srv.get_sample_sheet_from_bssh_run_files(api_url, sample_sheet_name)

    #  from current implementation, we will get all sample sheet from bssh run files, and create a sample sheet records for each file
    sample_sheet_contents = bssh_srv.get_all_sample_sheet_from_bssh_run_files(api_url)

    for sample_sheet_content in sample_sheet_contents:
        # check if the sample sheet already exists
        if SampleSheet.objects.filter(sequence=sequence, sample_sheet_name=sample_sheet_content['name']).exists():
            logger.info(f"Sample sheet {sample_sheet_content['name']} already exists for sequence {sequence.sequence_run_id}")
            continue

        # Convert content to JSON format with v2_samplesheet_to_json function
        content_dict = parse_samplesheet(sample_sheet_content['content'])

        SampleSheet.objects.create(
            sequence=sequence,
            sample_sheet_name=sample_sheet_content['name'],
            sample_sheet_content=content_dict,
        )

def get_sample_sheet_libraries(sample_sheet: SampleSheet):
    """
    Get the list of libraries (sample_ids) from the sample sheet's bclconvert_data

    Args:
        sample_sheet (SampleSheet): The sample sheet object containing the sample data

    Returns:
        list[str]: List of unique sample_ids from the bclconvert_data
    """
    bclconvert_data = sample_sheet.sample_sheet_content.get("bclconvert_data", [])
    # return empty list if no bclconvert_data
    if not bclconvert_data:
            return []

    # remove repeated value
    return list(dict.fromkeys(entry["sample_id"] for entry in bclconvert_data))
