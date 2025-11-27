import json
import logging
from dataclasses import dataclass
from typing import Optional

from sequence_run_manager.models import SampleSheet, Comment
from sequence_run_manager_proc.domain.events.srssc import SequenceRunSampleSheetChange, AWSEvent, Comment as CommentEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@dataclass
class SampleSheetDomain:
    _namespace = "orcabus.sequencerunmanager"
    sample_sheet: SampleSheet
    instrument_run_id: str
    sequence_run_id: str
    samplesheet_base64_gz: str
    comment: Optional[Comment] = None

    # flag to indicate if sample sheet changed
    sample_sheet_has_changed: bool = False

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def event_type(self) -> str:
        return SequenceRunSampleSheetChange.__name__

    def to_event(self) -> SequenceRunSampleSheetChange:
        comment_event = None
        if self.comment:
            comment_event = CommentEvent(
                comment=self.comment.comment,
                created_by=self.comment.created_by,
                created_at=self.comment.created_at,
            )
        return SequenceRunSampleSheetChange(
            instrumentRunId=self.instrument_run_id,
            sequenceRunId=self.sequence_run_id,
            timeStamp=self.sample_sheet.association_timestamp,
            sampleSheetName=self.sample_sheet.sample_sheet_name,
            samplesheetBase64gz=self.samplesheet_base64_gz,
            comment=comment_event,
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
