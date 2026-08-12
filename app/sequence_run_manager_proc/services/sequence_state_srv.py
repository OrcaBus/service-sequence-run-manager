import logging

from django.db import transaction

from sequence_run_manager.models.sequence import Sequence
from sequence_run_manager.models.state import State
from sequence_run_manager_proc.domain.events.srsc import SequenceRunStateChange

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@transaction.atomic
def create_sequence_state_from_bssh_event(payload: dict) -> None:
    """
    Create SequenceState record from BSSH Run event payload
    """
    status = payload["status"]
    timestamp = payload["dateModified"]

    # get sequence by sequence_run_id
    sequence = Sequence.objects.get(sequence_run_id=payload["id"])

    # None by default
    comment = None

    State.objects.create(
        status=status, timestamp=timestamp, sequence=sequence, comment=comment
    )
    logger.info(
        f"Created new Sequence State (sequence_run_id={sequence.sequence_run_id}, status={status})"
    )


def map_sequence_run_new_state_to_srsc(
    sequence: Sequence, new_state: State
) -> SequenceRunStateChange:
    """
    Map a persisted sequence run state to a SequenceRunStateChange event.

    Sequence metadata comes from the Sequence row, while status comes from the
    newly created State row that triggered the API event.
    """
    return SequenceRunStateChange(
        id=sequence.orcabus_id,
        instrumentRunId=sequence.instrument_run_id,
        runVolumeName=sequence.run_volume_name or "",
        runFolderPath=sequence.run_folder_path or "",
        runDataUri=sequence.run_data_uri or "",
        sampleSheetName=sequence.sample_sheet_name or "",
        startTime=sequence.start_time,
        endTime=sequence.end_time or "",
        status=new_state.status or "",
    )
