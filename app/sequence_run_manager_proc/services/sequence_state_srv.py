import hashlib
import json
import logging

from django.db import transaction

from sequence_run_manager.models.sequence import Sequence
from sequence_run_manager.models.state import State
from sequence_run_manager_proc.domain.events.srsc import SequenceRunStateChange

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Semver of the SRSC event contract, emitted as `detail.version`.
#   1.1.0 -- `orcabusId` carries the Sequence OrcaBus id (it used to be `id`),
#            `id` became a content hash, and the optional `stateCreatedBy` was
#            added for user-created states.
SRSC_SCHEMA_VERSION = "1.1.0"


def get_srsc_hash(srsc: SequenceRunStateChange) -> str:
    """Content hash identifying an SRSC data event, for deduplication.

    Derived from the fields that make a state change distinct: the schema
    version, the sequence identity, the announced status and — for
    user-created states — the state's author. Timestamps are deliberately left
    out so that re-announcing an unchanged state yields the same id.

    An id that is already set is returned untouched, so calling this twice on
    the same event is a no-op.
    """
    if srsc.id:
        return srsc.id

    # Hash a canonical JSON object rather than the bare concatenated values:
    # field names and JSON quoting keep the boundaries between values intact,
    # so no two different field combinations can produce the same bytes (a
    # plain concatenation cannot tell ["ab", "c"] from ["a", "bc"]). Keys are
    # sorted by `json.dumps` so the digest is pinned to the field names, not to
    # the order they happen to be written in here.
    content = json.dumps(
        {
            "version": srsc.version,
            "orcabusId": srsc.orcabusId,
            "instrumentRunId": srsc.instrumentRunId,
            "status": srsc.status,
            "stateCreatedBy": srsc.stateCreatedBy,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # Not a security digest -- md5 is used only as a short, stable dedup key.
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


def _authorless_exclude(srsc: SequenceRunStateChange) -> set | None:
    """Fields to drop for system-originated states, which have no author."""
    return {"stateCreatedBy"} if srsc.stateCreatedBy is None else None


def srsc_event_detail(srsc: SequenceRunStateChange) -> dict:
    """Serialize an SRSC event to its EventBridge detail dict.

    `stateCreatedBy` is dropped for authorless states rather than being sent as
    an explicit null.
    """
    return srsc.model_dump(mode="json", exclude=_authorless_exclude(srsc))


def srsc_event_detail_json(srsc: SequenceRunStateChange) -> str:
    """Serialize an SRSC event to its EventBridge detail JSON string."""
    return srsc.model_dump_json(exclude=_authorless_exclude(srsc))


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

    Sequence metadata comes from the Sequence row, while status and author come
    from the newly created State row that triggered the API event. `id` is a
    content hash of the event; the Sequence is identified by `orcabusId`.
    """
    srsc = SequenceRunStateChange(
        id="",
        version=SRSC_SCHEMA_VERSION,
        orcabusId=sequence.orcabus_id,
        instrumentRunId=sequence.instrument_run_id,
        runVolumeName=sequence.run_volume_name or "",
        runFolderPath=sequence.run_folder_path or "",
        runDataUri=sequence.run_data_uri or "",
        sampleSheetName=sequence.sample_sheet_name,
        startTime=sequence.start_time,
        endTime=sequence.end_time,
        status=new_state.status or "",
        stateCreatedBy=new_state.created_by,
    )
    srsc.id = get_srsc_hash(srsc)
    return srsc
