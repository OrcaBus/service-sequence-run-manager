from django.db import transaction
from django.utils import timezone
import logging

from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager_proc.services.bssh_srv import BSSHService
logger = logging.getLogger(__name__)

ASSOCIATION_STATUS = "ACTIVE"



@transaction.atomic
def create_sequence_run_libraries_linking(sequence_run: Sequence, linked_libraries: list[str]):
    """
    Create sequence run libraries linking
    """

    if linked_libraries:
        for library_id in linked_libraries:
                # create the library association
                LibraryAssociation.objects.create(
                    sequence=sequence_run,
                    library_id=library_id,
                    association_date=timezone.now(),  # Use timezone-aware datetime
                    status=ASSOCIATION_STATUS,
                )
        logger.info(f"Library associations created for sequence run {sequence_run.sequence_run_id}, linked libraries: {linked_libraries}")
    else:
        logger.info(f"No libraries found for sequence run {sequence_run.sequence_run_id}")

def update_sequence_run_libraries_linking(sequence_run: Sequence, linked_libraries: list[str]):
    """
    Update sequence run libraries linking
    """
    if LibraryAssociation.objects.filter(sequence=sequence_run).exists() and linked_libraries:
        existing_libraries = LibraryAssociation.objects.filter(sequence=sequence_run).values_list('library_id', flat=True)
        if existing_libraries and set(existing_libraries) == set(linked_libraries):
            logger.info(f"Library associations already exist for sequence run {sequence_run.sequence_run_id}, linked libraries: {linked_libraries}")
            return
        else:
            LibraryAssociation.objects.filter(sequence=sequence_run).delete()
            logger.info(f"Library associations deleted for sequence run {sequence_run.sequence_run_id}, linked libraries: {linked_libraries}")
    return create_sequence_run_libraries_linking(sequence_run, linked_libraries)

def check_or_create_sequence_run_libraries_linking_from_bssh_event(payload: dict):
    """
    Check if libraries are linked to the sequence run;
    if not, create the linking
    """
    assert payload["id"] is not None, "sequence run id is required"

    sequence_run = Sequence.objects.get(sequence_run_id=payload["id"])
    if not sequence_run:
        logger.error(f"Sequence run {payload['id']} not found when checking or creating sequence run libraries linking")
        raise ValueError(f"Sequence run {payload['id']} not found")

    linked_libraries = []
    sample_sheet = SampleSheet.objects.get(sequence=sequence_run)
    if sample_sheet:
        logger.info(f"Sample sheet found for sequence run {sequence_run.sequence_run_id}, fetching libraries from sample sheet")
        bclconvert_data = sample_sheet.sample_sheet_content.get("bclconvert_data", [])
        # return empty list if no bclconvert_data
        if not bclconvert_data:
            logger.info(f"No libraries found from sample sheet for sequence run {sequence_run.sequence_run_id}")
        else:
            # remove repeated value
            linked_libraries = list(dict.fromkeys(entry["sample_id"] for entry in bclconvert_data))
            logger.info(f"Libraries found from sample sheet for sequence run {sequence_run.sequence_run_id}, linked libraries: {linked_libraries}")
    else:
        logger.info(f"No sample sheet found for sequence run {sequence_run.sequence_run_id}, fetching libraries from bssh")
        bssh_srv = BSSHService()
        run_details = bssh_srv.get_run_details(sequence_run.api_url)
        linked_libraries = BSSHService.get_libraries_from_run_details(run_details)

    # if libraries are already linked, check if the libraries are the same
    if LibraryAssociation.objects.filter(sequence=sequence_run).exists() and linked_libraries:
        existing_libraries = LibraryAssociation.objects.filter(sequence=sequence_run).values_list('library_id', flat=True)
        if set(existing_libraries) == set(linked_libraries):
            logger.info(f"Library associations already exist for sequence run {sequence_run.sequence_run_id}, linked libraries: {linked_libraries}")
            return
        else:
            LibraryAssociation.objects.filter(sequence=sequence_run).delete()

    return create_sequence_run_libraries_linking(sequence_run, linked_libraries)

@transaction.atomic
def update_sequence_run_libraries_linking_from_srllc_event(event_detail: dict):
    """
    This function is used to check or create sequence run libraries linking from event details(SRLLC)
    event detail example:
    {
    "sequenceRunId": "r.1234567890ABCDEFGHIJKLMN", // orcabusid for the sequence run (fake run)
    "linkedLibraries": [
                "L2000000",
                "L2000001",
                "L2000002"
                ]
    }
    """
    assert event_detail["sequenceRunId"] is not None, "sequence run id is required"
    assert event_detail["linkedLibraries"] is not None, "linked libraries are required"

    sequence_run = Sequence.objects.get(sequence_run_id=event_detail["sequenceRunId"])
    if not sequence_run:
        logger.error(f"Sequence run {event_detail['sequenceRunId']} not found when checking or creating sequence run libraries linking")
        raise ValueError(f"Sequence run {event_detail['sequenceRunId']} not found")

    linked_libraries = event_detail["linkedLibraries"]

    return update_sequence_run_libraries_linking(sequence_run, linked_libraries)

# metadata manager service
# TODO ( thinking about if this is necessary):
#   1. check if the library is exist/active in the metadata manager
#   2. get the library details (library id) from the metadata manager
#   3. create the library record in the database

# def get_libraries_from_metadata_manager(auth_header: str, library_id_array: list[str]):
#     """
#     Get libraries from metadata manager:
#     return a list of dicts with the following keys:
#     [
#         {
#         "orcabusId": "string",
#         "projectSet": [
#             ...
#         ],
#         "sample": {
#             ...
#         },
#         "subject": {
#             ...
#         },
#         "libraryId": "string",
#         "phenotype": "normal",
#         "workflow": "clinical",
#         "quality": "very-poor",
#         "type": "10X",
#         "assay": "string",
#         "coverage": 0,
#         "overrideCycles": "string"
#         }
#     ]
#     """
#     try:
#         metadata_response = get_metadata_record_from_array_of_field_name(auth_header=auth_header,
#                                                                          field_name='library_id',
#                                                                          value_list=library_id_array)
#     except Exception as e:
#         raise Exception("Fail to fetch metadata api for library id in the sample sheet")

#     return metadata_response


# def get_metadata_record_from_array_of_field_name(auth_header: str, field_name: str,
#                                                  value_list: List[str]):
#     """
#     Get metadata record from array of field name
#     """
#     METADATA_DOMAIN_NAME = os.environ.get("METADATA_DOMAIN_NAME", "metadata.dev.umccr.org")
#     METADATA_API_PATH = 'api/v1/library'
#     # Define header request
#     headers = {
#         'Authorization': auth_header
#     }

#     # Removing any duplicates for api efficiency
#     value_list = list(set(value_list))

#     # Result variable
#     query_result = []

#     max_number_of_library_per_api_call = 300
#     for i in range(0, len(value_list), max_number_of_library_per_api_call):

#         # Define start and stop element from the list
#         start_index = i
#         end_index = start_index + max_number_of_library_per_api_call

#         array_to_process = value_list[start_index:end_index]

#         # Define query string
#         query_param_string = f'&{field_name}='.join(array_to_process)
#         query_param_string = f'?{field_name}=' + query_param_string  # Appending name at the beginning

#         query_param_string = query_param_string + f'&rowsPerPage=1000'  # Add Rows per page (1000 is the maximum rows)

#         url = f"https://{METADATA_DOMAIN_NAME.strip('.')}/{METADATA_API_PATH.strip('/')}/{query_param_string}"
#         # Make sure no data is left, looping data until the end
#         while url is not None:
#             req = urllib.request.Request(url, headers=headers)
#             with urllib.request.urlopen(req) as response:
#                 if response.status < 200 or response.status >= 300:
#                     raise ValueError(f'Non 20X status code returned')

#                 response_json = json.loads(response.read().decode())
#                 query_result.extend(response_json["results"])
#                 url = response_json["links"]["next"]
#     return query_result
