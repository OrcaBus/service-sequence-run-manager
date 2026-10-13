import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from sequence_run_manager_proc.domain.events.srllc import (
    SequenceRunLibraryLinkingChange,
    AWSEvent,
)
from django.utils import timezone

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Semver of the SRLLC event contract, emitted as `detail.version`.
#   1.1.0 -- added `version` and the content hash `id`.
SRLLC_SCHEMA_VERSION = "1.1.0"


def get_srllc_hash(srllc: SequenceRunLibraryLinkingChange) -> str:
    """Content hash identifying an SRLLC data event, for deduplication.

    Derived from the schema version, the sequence run and the linked libraries.
    The libraries are hashed as a sorted set -- the same way the linking itself
    is compared -- so their order does not matter. `timeStamp` is deliberately
    left out so that re-announcing an unchanged linking yields the same id.

    An id that is already set is returned untouched, so calling this twice on
    the same event is a no-op.
    """
    if srllc.id:
        return srllc.id

    # Canonical JSON for the same reasons as `get_srsc_hash`: field names keep
    # the boundaries between values intact and sorted keys pin the digest.
    content = json.dumps(
        {
            "version": srllc.version,
            "instrumentRunId": srllc.instrumentRunId,
            "sequenceRunId": srllc.sequenceRunId,
            "linkedLibraries": sorted(set(srllc.linkedLibraries)),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # Not a security digest -- md5 is used only as a short, stable dedup key.
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass
class LibraryLinkingDomain:
    _namespace = "orcabus.sequencerunmanager"
    instrument_run_id: str
    sequence_run_id: str
    linked_libraries: list[str]
    timestamp: datetime = timezone.now()

    # flag to indicate if library linking changed
    library_linking_has_changed: bool = False

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def event_type(self) -> str:
        return SequenceRunLibraryLinkingChange.__name__

    def to_event(self) -> SequenceRunLibraryLinkingChange:
        srllc = SequenceRunLibraryLinkingChange(
            id="",
            version=SRLLC_SCHEMA_VERSION,
            instrumentRunId=self.instrument_run_id,
            sequenceRunId=self.sequence_run_id,
            timeStamp=self.timestamp,
            linkedLibraries=self.linked_libraries,
        )
        srllc.id = get_srllc_hash(srllc)
        return srllc

    def to_event_with_envelope(self) -> AWSEvent:
        return AWSEvent(
            source=self.namespace,
            detail_type=self.event_type,
            detail=self.to_event(),
        )

    def to_put_events_request_entry(
        self, event_bus_name: str, trace_header: str = ""
    ) -> dict:
        """Convert Domain event with envelope to Entry dict struct of PutEvent API"""
        domain_event_with_envelope = self.to_event_with_envelope()
        entry = {
            "Detail": domain_event_with_envelope.detail.model_dump_json(),
            "DetailType": domain_event_with_envelope.detail_type,
            "Resources": [],
            "Source": domain_event_with_envelope.source,
            "EventBusName": event_bus_name,
        }
        if trace_header:
            entry.update(TraceHeader=trace_header)
        return entry
