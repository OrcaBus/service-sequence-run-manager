from django.db import transaction
from django.utils import timezone
import ulid
import logging
import base64

from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment
from sequence_run_manager_proc.services.bssh_srv import BSSHService
from sequence_run_manager_proc.services.sequence_library_srv import ASSOCIATION_STATUS
from sequence_run_manager_proc.services.sequence_library_srv import update_sequence_run_libraries_linking

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

    assert event_detail["instrumentRunId"] is not None, "instrument run id is required"
    assert event_detail["sampleSheetName"] is not None, "sample sheet name is required"
    assert event_detail["samplesheetbase64gz"] is not None, "sample sheet base64 is required"

    sequence_run = None
    instrument_run_id = event_detail["instrumentRunId"]
    samplesheet_name = event_detail["sampleSheetName"]

    #  step 1: check if the sequence run exists, create a fake sequence run if not
    if event_detail["sequenceRunId"]:
        sequence_run = Sequence.objects.get(sequence_run_id=event_detail["sequenceRunId"])
        if not sequence_run:
            logger.error(f"Sequence run {event_detail['sequenceRunId']} not found when checking or creating sequence sample sheet from event")
            raise ValueError(f"Sequence run {event_detail['sequenceRunId']} not found")
    else:
        # create a fake sequence run
        sequence_run = Sequence(
            instrument_run_id=instrument_run_id,
            sequence_run_id="r."+ulid.new().str,
            sample_sheet_name=samplesheet_name,
            start_time=timezone.now()  # add start time to record the time when the (ghost) sequence run is created
        )
        logger.info(f"Created a fake sequence run {sequence_run.sequence_run_id} for instrument run {instrument_run_id}")


    content_base64 = event_detail["samplesheetbase64gz"]
    content_dict = parse_samplesheet(base64.b64decode(content_base64))

    # step 2: create a sample sheet for the sequence run
    sample_sheet = SampleSheet.objects.create(
        sequence=sequence_run,
        sample_sheet_name=samplesheet_name,
        sample_sheet_content=content_dict,
    )

    # comment object needed for sample sheet, refer: https://github.com/umccr/orcabus/issues/947
    # step 3: create a comment for the sample sheet
    if event_detail["comment"]:
        Comment.objects.create(
            association_id=sample_sheet.orcabus_id,
            comment=event_detail["comment"]["comment"],
            created_by=event_detail["comment"]["created_by"],
        )
        logger.info(f"Created a comment for sample sheet {samplesheet_name}")
    else:
        logger.info(f"No comment provided for sample sheet {event_detail['sampleSheetName']}")

    # step 4: check if there is library linking change, if there is any change, create library associations and emit event to event bridge
    linking_libraries = list(dict.fromkeys(entry["sample_id"] for entry in content_dict.get("bclconvert_data", [])))
    if linking_libraries:
        # update the sequence run libraries linking
        update_sequence_run_libraries_linking(sequence_run, linking_libraries)
    else:
        logger.info(f"No library linking found in samplesheet for sequence run {sequence_run.sequence_run_id}")

def create_sequence_sample_sheet_from_reconversion_event(payload: dict):
    """
    Check if the sample sheet for a sequence exists;
    if not, create it
    """
    assert payload["id"] is not None, "sequence run id is required"
    assert payload["apiUrl"] is not None, "api url is required"
    assert payload["sampleSheetName"] is not None, "sample sheet name is required"

    sequence_run = Sequence.objects.get(sequence_run_id=payload["id"])
    if not sequence_run:
        logger.error(f"Sequence run {payload['id']} not found when checking or creating sequence sample sheet")
        raise ValueError(f"Sequence run {payload['id']} not found")

    api_url = payload["apiUrl"]
    sample_sheet_name = payload["sampleSheetName"]
    bssh_srv = BSSHService()
    sample_sheet_content = bssh_srv.get_sample_sheet_from_bssh_run_files(api_url, sample_sheet_name)
    if not sample_sheet_content:
        logger.error(f"Sample sheet {sample_sheet_name} not found for sequence {sequence_run.sequence_run_id}")
        raise ValueError(f"Sample sheet {sample_sheet_name} not found")

    content_dict = parse_samplesheet(sample_sheet_content)

    SampleSheet.objects.create(
        sequence=sequence_run,
        sample_sheet_name=sample_sheet_name,
        sample_sheet_content=content_dict,
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
