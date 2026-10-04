import os
import json
import logging
from dataclasses import dataclass
from typing import Optional
import hashlib

from sequence_run_manager.models import SampleSheet, Comment
from sequence_run_manager_proc.domain.events.srssc import (
    SequenceRunSampleSheetChange,
    AWSEvent,
)
from sequence_run_manager.settings.base import API_VERSION

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Semver of the SRSSC event contract, emitted as `detail.version`.
#   1.1.0 -- added `version` and the content hash `id`.
SRSSC_SCHEMA_VERSION = "1.1.0"


def get_srssc_hash(srssc: SequenceRunSampleSheetChange) -> str:
    """Content hash identifying an SRSSC data event, for deduplication.

    Derived from the fields that identify the announced sample sheet: the schema
    version, the sequence run, the sample sheet record (`apiUrl` carries its
    OrcaBus id), its name and its content checksum. `timeStamp` and the
    free-text `description` are deliberately left out so that re-announcing the
    same sample sheet yields the same id.

    An id that is already set is returned untouched, so calling this twice on
    the same event is a no-op.
    """
    if srssc.id:
        return srssc.id

    # Canonical JSON for the same reasons as `get_srsc_hash`: field names keep
    # the boundaries between values intact and sorted keys pin the digest.
    content = json.dumps(
        {
            "version": srssc.version,
            "instrumentRunId": srssc.instrumentRunId,
            "sequenceRunId": srssc.sequenceRunId,
            "sampleSheetName": srssc.sampleSheetName,
            "apiUrl": srssc.apiUrl,
            "checksum": srssc.checksum,
            "checksumType": srssc.checksumType,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # Not a security digest -- md5 is used only as a short, stable dedup key.
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


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

    def _generate_sample_sheet_checksum(
        self, sample_sheet_content_original: str
    ) -> str:
        """
        Generate a SHA256 checksum from sample sheet content (JSON format).

        Args:
            sample_sheet_content_original: Original CSV content of the sample sheet

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
            calculated_checksum = hashlib.sha256(sample_sheet_content_original.encode('utf-8')).hexdigest()

            # Verify integrity
            if calculated_checksum == checksum_from_event:
                print("Sample sheet content is valid!")
            else:
                print("WARNING: Sample sheet content checksum mismatch!")
        """
        if not sample_sheet_content_original:
            return ""
        try:
            # Generate SHA256 hash from original CSV content
            return hashlib.sha256(
                sample_sheet_content_original.encode("utf-8")
            ).hexdigest()
        except Exception as e:
            logger.warning(
                f"Failed to generate checksum from sample sheet content: {str(e)}"
            )
            return ""

    def to_event(self) -> Optional[SequenceRunSampleSheetChange]:
        sequenceRunManagerBaseApiUrl = os.environ["SEQUENCE_RUN_MANAGER_BASE_API_URL"]
        api_base = f"/api/{API_VERSION}/"
        api_url = f"{sequenceRunManagerBaseApiUrl}{api_base}sample_sheet/{self.sample_sheet.orcabus_id}/"
        checksum = self._generate_sample_sheet_checksum(
            self.sample_sheet.sample_sheet_content_original
        )
        srssc = SequenceRunSampleSheetChange(
            id="",
            version=SRSSC_SCHEMA_VERSION,
            instrumentRunId=self.instrument_run_id,
            sequenceRunId=self.sequence_run_id,
            timeStamp=self.sample_sheet.association_timestamp,
            sampleSheetName=self.sample_sheet.sample_sheet_name,
            apiUrl=api_url,
            checksum=checksum,
            checksumType="sha256",
            description=self.description,
        )
        srssc.id = get_srssc_hash(srssc)
        return srssc

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
