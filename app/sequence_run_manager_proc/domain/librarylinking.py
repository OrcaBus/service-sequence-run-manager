import logging
from dataclasses import dataclass
from datetime import datetime
from sequence_run_manager_proc.domain.events.srllc import SequenceRunLibraryLinkingChange, AWSEvent
from django.utils import timezone
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        return SequenceRunLibraryLinkingChange(
            instrumentRunId=self.instrument_run_id,
            sequenceRunId=self.sequence_run_id,
            timeStamp=self.timestamp,
            linkedLibraries=self.linked_libraries,
        )

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
