import json
import logging
from dataclasses import dataclass

from sequence_run_manager.models import SampleSheet
from sequence_run_manager_proc.domain.events.srssc import SequenceRunSampleSheetChange, AWSEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@dataclass
class SampleSheetDomain:
    _namespace = "orcabus.sequencerunmanager"
    sample_sheet: SampleSheet
    instrument_run_id: str
    sequence_run_id: str
    samplesheet_base64_gz: str

    # flag to indicate if sample sheet changed
    sample_sheet_has_changed: bool = False

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def event_type(self) -> str:
        return SequenceRunSampleSheetChange.__name__

    def to_event(self) -> SequenceRunSampleSheetChange:
        return SequenceRunSampleSheetChange(
            instrumentRunId=self.instrument_run_id,
            sequenceRunId=self.sequence_run_id,
            timeStamp=self.sample_sheet.association_timestamp,
            sampleSheetName=self.sample_sheet.sample_sheet_name,
            samplesheetBase64gz=self.samplesheet_base64_gz,
            comment=None,
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
