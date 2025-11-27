import os
import json
import logging
from dataclasses import dataclass
from typing import Optional
import hashlib

from sequence_run_manager.models import SampleSheet, Comment
from sequence_run_manager_proc.domain.events.srssc import SequenceRunSampleSheetChange, AWSEvent
from sequence_run_manager.urls.base import api_base

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@dataclass
class SampleSheetDomain:
    _namespace = "orcabus.sequencerunmanager"
    sample_sheet: SampleSheet
    instrument_run_id: str
    sequence_run_id: str
    description: Optional[str] = None

    # flag to indicate if sample sheet changed
    sample_sheet_has_changed: bool = False

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def event_type(self) -> str:
        return SequenceRunSampleSheetChange.__name__

    def _generate_sample_sheet_checksum(self, sample_sheet_content: dict) -> str:
        """
        Generate a SHA256 checksum from sample sheet content (JSON format).

        Args:
            sample_sheet_content: Dictionary containing the sample sheet content (JSON format)

        Returns:
            str: SHA256 checksum as hexadecimal string, or empty string if content is None/empty

        Example usage:
            # In another service consuming SequenceRunSampleSheetChange events:
            event_detail = event["detail"]
            checksum_from_event = event_detail["checksum"]

            # Fetch sample sheet from API
            response = requests.get(event_detail["apiUrl"])
            sample_sheet_data = response.json()

            # Generate checksum from fetched content
            calculated_checksum = generate_sample_sheet_checksum(sample_sheet_data["sample_sheet_content"])

            # Verify integrity
            if calculated_checksum == checksum_from_event:
                print("Sample sheet content is valid!")
            else:
                print("WARNING: Sample sheet content checksum mismatch!")
        """
        if not sample_sheet_content:
            return ""

        try:
            # Convert to JSON string with sorted keys and no whitespace for consistency
            # This must match exactly how checksum is generated in to_event()
            json_str = json.dumps(
                sample_sheet_content,
                sort_keys=True,
                separators=(',', ':'),  # Compact format, no spaces
                ensure_ascii=False
            )
            # Generate SHA256 hash
            return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to generate checksum from sample sheet content: {str(e)}")
            return ""

    def to_event(self) -> Optional[SequenceRunSampleSheetChange]:
        sequenceRunManagerBaseApiUrl = os.environ["SEQUENCE_RUN_MANAGER_BASE_API_URL"]
        sequence_id = self.sample_sheet.sequence.orcabus_id
        api_url = f"{sequenceRunManagerBaseApiUrl}{api_base}sequence_run/{sequence_id}/sample_sheet/"
        checksum = self._generate_sample_sheet_checksum(self.sample_sheet.sample_sheet_content)
        return SequenceRunSampleSheetChange(
            instrumentRunId=self.instrument_run_id,
            sequenceRunId=self.sequence_run_id,
            timeStamp=self.sample_sheet.association_timestamp,
            sampleSheetName=self.sample_sheet.sample_sheet_name,
            apiUrl=api_url,
            checksum=checksum,
            description=self.description,
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
