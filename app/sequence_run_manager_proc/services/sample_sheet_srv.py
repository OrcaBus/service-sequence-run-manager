from tkinter import N
from django.db import transaction
from django.utils import timezone
import ulid
import logging
import base64
import gzip
import json
from typing import Optional
from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment, TargetType
from sequence_run_manager_proc.domain.samplesheet import SampleSheetDomain
from sequence_run_manager_proc.services.bssh_srv import BSSHService
from sequence_run_manager_proc.services.sequence_library_srv import update_sequence_run_libraries_linking
from sequence_run_manager_proc.services.sequence_srv import SequenceConfig

from v2_samplesheet_parser.functions.parser import parse_samplesheet

logger = logging.getLogger(__name__)

def create_sequence_sample_sheet_from_bssh_event(payload: dict)->Optional[SampleSheetDomain]:
    """
    Check if the sample sheet for a sequence exists;
    if not, create it by making BSSH API call.
    If there's an error (API call error, no files, no content), log the error and continue.
    """
    assert payload["id"] is not None, "sequence run id is required"

    try:
        sequence_run = Sequence.objects.get(sequence_run_id=payload["id"])
    except Sequence.DoesNotExist:
        logger.error(f"Sequence run {payload['id']} not found when checking or creating sequence sample sheet")
        return None

    # check if this sequence run already has sample sheet, if so, skip creation
    if SampleSheet.objects.filter(sequence=sequence_run).exists():
        logger.info(f"Sample sheet already exists for sequence {payload['id']}, skipping creation")
        return None

    try:
        sample_sheet, samplesheet_content = create_sequence_sample_sheet(sequence_run, payload)
        if not sample_sheet or not samplesheet_content:
            logger.error(f"Error creating sample sheet or no sample sheet name found for sequence {payload['id']}.")
            return None
        return SampleSheetDomain(
            instrument_run_id=sequence_run.instrument_run_id,
            sequence_run_id=sequence_run.sequence_run_id,
            sample_sheet=sample_sheet,
            description=f"Sample sheet {sample_sheet.sample_sheet_name} created for sequence {sequence_run.sequence_run_id} from BSSH event",
            sample_sheet_has_changed=True,
        )
    except Exception as e:
        logger.error(f"Error creating sample sheet for sequence {payload['id']}: {str(e)}. Will retry on next state change.")
        return None

def create_sequence_sample_sheet_from_srssc_event(event_detail: dict):
    """
    Check or create sequence sample sheet from event detail
    """

    assert event_detail["instrumentRunId"] is not None, "instrument run id is required"
    assert event_detail["sampleSheetName"] is not None, "sample sheet name is required"
    assert event_detail["samplesheetBase64gz"] is not None, "sample sheet base64 is required"

    sequence_run = None
    instrument_run_id = event_detail["instrumentRunId"]
    samplesheet_name = event_detail["sampleSheetName"]

    #  step 1: check if the sequence run exists, create a fake sequence run if not
    if event_detail.get("sequenceRunId") is not None:
        try:
            sequence_run = Sequence.objects.get(sequence_run_id=event_detail["sequenceRunId"])
        except Sequence.DoesNotExist:
            logger.error(f"Sequence run {event_detail['sequenceRunId']} not found when checking or creating sequence sample sheet from SRSSE event")
            return
    else:
        # create a fake sequence run
        sequence_run = Sequence.objects.create(
            instrument_run_id=instrument_run_id,
            sequence_run_id="r."+ulid.new().str,
            sample_sheet_name=samplesheet_name,
            start_time=timezone.now()  # add start time to record the time when the (ghost) sequence run is created
        )
        logger.info(f"Created a fake sequence run {sequence_run.sequence_run_id} for instrument run {instrument_run_id}")


    content_base64_gz = event_detail["samplesheetBase64gz"]
    # Decode from base64+gzip to get original CSV string
    original_csv_content = gzip.decompress(base64.b64decode(content_base64_gz)).decode('utf-8')
    content_dict = parse_samplesheet(original_csv_content)

    # step 2: create a sample sheet for the sequence run
    sample_sheet = SampleSheet.objects.create(
        sequence=sequence_run,
        sample_sheet_name=samplesheet_name,
        sample_sheet_content=content_dict,
        sample_sheet_content_original=original_csv_content,  # Store original CSV as UTF-8 string
    )

    # comment object needed for sample sheet, refer: https://github.com/umccr/orcabus/issues/947
    # step 3: create a comment for the sample sheet
    if event_detail.get("comment") is not None:
        Comment.objects.create(
            target_id=sample_sheet.orcabus_id,
            target_type=TargetType.SAMPLE_SHEET,
            comment=event_detail["comment"]["comment"],
            created_by=event_detail["comment"]["createdBy"],
        )
        logger.info(f"Created a comment for sample sheet {samplesheet_name}")
    else:
        logger.info(f"No comment provided for sample sheet {event_detail['sampleSheetName']}")

    # step 4: check if there is library linking change, if there is any change, create library associations and emit event to event bridge
    linking_libraries = list(dict.fromkeys(entry["sample_id"] for entry in content_dict.get("bclconvert_data", [])))
    if linking_libraries:
        # update the sequence run libraries linking
        try:
            update_sequence_run_libraries_linking(sequence_run, linking_libraries)
        except Exception as e:
            logger.error(f"Error updating sequence run libraries linking for sequence {sequence_run.sequence_run_id}: {str(e)}. Will retry on next state change.")
            return
    else:
        logger.info(f"No library linking found in samplesheet for sequence run {sequence_run.sequence_run_id}")

def check_sequence_sample_sheet_from_bssh_event(payload: dict)->Optional[SampleSheetDomain]:
    """
    Check if the sample sheet for a sequence exists;
    if not, create it by making BSSH API call.
    If there's an error (API call error, no files, no content), log the error and continue.
    if sample shett exist ,will check if the content is the same, if different, update the sample sheet content, if not return none, if not exists, create a new sample sheet
    """
    assert payload["id"] is not None, "sequence run id is required"
    if not payload.get("apiUrl", None):
        logger.warning(f"No API URL provided for sequence {payload['id']}, skipping sample sheet check")
        return None
    if not payload.get("sampleSheetName", None):
        logger.warning(f"No sample sheet name provided for sequence {payload['id']}, skipping sample sheet check")
        return None

    try:
        sequence_run = Sequence.objects.get(sequence_run_id=payload["id"])
    except Sequence.DoesNotExist:
        logger.error(f"Sequence run {payload['id']} not found when checking or creating sequence sample sheet from bssh event")
        return None

    api_url = payload["apiUrl"]
    sample_sheet_name = payload["sampleSheetName"]

    try:
        bssh_srv = BSSHService()
        sample_sheet_content = bssh_srv.get_sample_sheet_from_bssh_run_files(api_url, sample_sheet_name)
    except Exception as e:
        logger.error(f"Error getting sample sheet {sample_sheet_name} from BSSH API for sequence {sequence_run.sequence_run_id} at {api_url}: {str(e)}.")
        return None

    if not sample_sheet_content:
        logger.warning(f"Sample sheet {sample_sheet_name} not found for sequence {sequence_run.sequence_run_id} at {api_url}.")
        return None

    try:
        content_dict = parse_samplesheet(sample_sheet_content)
    except Exception as e:
        logger.error(f"Error parsing sample sheet {sample_sheet_name} for sequence {sequence_run.sequence_run_id}: {str(e)}.")
        return None

    # Check if sample sheet already exists , if already exists, compare the content, if different, update the sample sheet content, if not return none
    # if not exists, create a new sample sheet
    if SampleSheet.objects.filter(sequence=sequence_run, sample_sheet_name=sample_sheet_name).exists():
        sample_sheet_obj = SampleSheet.objects.get(sequence=sequence_run, sample_sheet_name=sample_sheet_name)
        if sample_sheet_obj.sample_sheet_content != content_dict:
            logger.info(f"Sample sheet {sample_sheet_name} content is different for sequence {sequence_run.sequence_run_id} from bssh event")
            # create a new sample sheet object
            sample_sheet_new_obj = SampleSheet(
                sequence=sequence_run,
                sample_sheet_name=sample_sheet_name,
                sample_sheet_content=content_dict,
                sample_sheet_content_original=sample_sheet_content,  # Update original CSV as UTF-8 string
            )
            sample_sheet_new_obj.save()
            logger.info(f"New sample sheet {sample_sheet_new_obj.sample_sheet_name} created for sequence {sequence_run.sequence_run_id} from bssh event")
            return SampleSheetDomain(
                instrument_run_id=sequence_run.instrument_run_id,
                sequence_run_id=sequence_run.sequence_run_id,
                sample_sheet=sample_sheet_new_obj,
                description=f"New sample sheet {sample_sheet_new_obj.sample_sheet_name} created for sequence {sequence_run.sequence_run_id} from bssh event",
                sample_sheet_has_changed=True,
            )
        else:
            logger.info(f"Sample sheet {sample_sheet_name} content is the same for sequence {sequence_run.sequence_run_id} from bssh event")
            return None
    else:
        try:
            sample_sheet_obj = SampleSheet(
                sequence=sequence_run,
                sample_sheet_name=sample_sheet_name,
                sample_sheet_content=content_dict,
                sample_sheet_content_original=sample_sheet_content,  # Store original CSV as UTF-8 string
            )
            sample_sheet_obj.save()
            logger.info(f"Successfully created sample sheet {sample_sheet_obj.sample_sheet_name} for sequence {sequence_run.sequence_run_id} from bssh event")
            return SampleSheetDomain(
                instrument_run_id=sequence_run.instrument_run_id,
                sequence_run_id=sequence_run.sequence_run_id,
                sample_sheet=sample_sheet_obj,
                description=f"New sample sheet {sample_sheet_obj.sample_sheet_name} created for sequence {sequence_run.sequence_run_id} from bssh event",
                sample_sheet_has_changed=True,
            )
        except Exception as e:
            logger.error(f"Error creating sample sheet {sample_sheet_name} for sequence {sequence_run.sequence_run_id}: {str(e)}. Will retry on next state change.")
            return None

@transaction.atomic
def create_sequence_sample_sheet(sequence: Sequence, payload: dict) -> tuple[Optional[SampleSheet], Optional[str]]:
    """
    Create a sample sheet for a sequence.
    Check if sample sheet already exists before making API call.
    If API call fails or returns no content, log error and return gracefully.
    """
    api_url = payload.get("apiUrl")
    if not api_url:
        logger.warning(f"No API URL provided for sequence {sequence.sequence_run_id}, skipping sample sheet creation")
        return None, None

    try:
        bssh_srv = BSSHService()
        # Get all sample sheet from bssh run files
        sample_sheet_contents = bssh_srv.get_all_sample_sheet_from_bssh_run_files(api_url)
    except Exception as e:
        logger.error(f"Error getting sample sheet files from BSSH API for sequence {sequence.sequence_run_id} at {api_url}: {str(e)}. Will retry on next state change.")
        raise e

    if not sample_sheet_contents:
        logger.warning(f"No sample sheet files found for sequence {sequence.sequence_run_id} at {api_url}. Will retry on next state change.")
        return None, None

    # Build list of SampleSheet objects to create, then bulk_create at the end
    sample_sheet_objs_to_create = []

    # instance and content for sequence sample sheet
    sequence_samplesheet:SampleSheet = None
    sequence_samplesheet_content: Optional[str] = None
    sequence_samplesheet_name: Optional[str] = sequence.sample_sheet_name

    for sample_sheet_content in sample_sheet_contents:
        # Check if the sample sheet already exists
        if SampleSheet.objects.filter(sequence=sequence, sample_sheet_name=sample_sheet_content['name']).exists():
            logger.info(f"Sample sheet {sample_sheet_content['name']} already exists for sequence {sequence.sequence_run_id}")
            continue

        # Check if content is empty or None
        if not sample_sheet_content.get('content'):
            logger.warning(f"Sample sheet {sample_sheet_content.get('name', 'unknown')} has no content for sequence {sequence.sequence_run_id}, skipping")
            continue

        try:
            # Convert content to JSON format with v2_samplesheet_to_json function
            content_dict = parse_samplesheet(sample_sheet_content['content'])

            sample_sheet_obj = SampleSheet(
                sequence=sequence,
                sample_sheet_name=sample_sheet_content['name'],
                sample_sheet_content=content_dict,
                sample_sheet_content_original=sample_sheet_content['content'],  # Store original CSV as UTF-8 string
            )
            sample_sheet_objs_to_create.append(sample_sheet_obj)

            if sequence_samplesheet_name != None and sequence_samplesheet_name != SequenceConfig.UNKNOWN_VALUE and sample_sheet_content['name'] == sequence_samplesheet_name:
                sequence_samplesheet = sample_sheet_obj
                sequence_samplesheet_content = sample_sheet_content['content']

        except Exception as e:
            logger.error(f"Error parsing sample sheet {sample_sheet_content.get('name', 'unknown')} for sequence {sequence.sequence_run_id}: {str(e)}. Continuing with next sample sheet.")
            continue

    if sample_sheet_objs_to_create:
        try:
            SampleSheet.objects.bulk_create(sample_sheet_objs_to_create)
            for obj in sample_sheet_objs_to_create:
                logger.info(f"Successfully created sample sheet {obj.sample_sheet_name} for sequence {sequence.sequence_run_id}")
            return sequence_samplesheet, sequence_samplesheet_content
        except Exception as e:
            logger.error(f"Error bulk creating sample sheets for sequence {sequence.sequence_run_id}: {str(e)}.")
            return None, None
    else:
        logger.info(f"No sample sheets to create for sequence {sequence.sequence_run_id}.")
        return None, None


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
