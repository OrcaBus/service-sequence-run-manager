import os

import django

django.setup()

# --- keep ^^^ at top of the module

import logging

from sequence_run_manager_proc.domain.events import srssu
from sequence_run_manager_proc.services import sample_sheet_srv
from libumccr import libjson
from libumccr.aws import libeb

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def event_handler(event, context):
    """
    This lambda function is used to handle the sample sheet event from the event bus

    1) SRSSU event payload dict (sent by other services, i.e. any source but orcabus.sequencerunmanager)
    {
        "version": "0",
        "id": "12345678-90ab-cdef-1234-567890abcdef",
        "detail-type": "SequenceRunSampleSheetUpdate",
        "source": "orcabus.manual",
        "account": "000000000000",
        "time": "2025-03-00T00:00:00Z",
        "region": "ap-southeast-2",
        "resources": [],
        "detail": {
            "id": "<hash of the event data>", // optional
            "version": "1.0.0", // optional, the SRSSU schema version
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "sequenceRunId": "r.1234567890abcdefghijklmn", // optional, a fake sequence run is created if omitted
            "timeStamp": "2025-03-01T00:00:00.000000+00:00",
            "sampleSheetName": "sampleSheet_v2.csv",
            "samplesheetBase64gz": "base64_encoded_samplesheet_gzip........",
            "comment": {
                "comment": "comment",
                "createdBy": "user",
            }
        }
    }
    The sample sheet is stored and announced as a SequenceRunSampleSheetChange (SRSSC) event,
    followed by a SequenceRunLibraryLinkingChange (SRLLC) event when the library linking changed.

    2) WRSC event payload dict
    {
        "version": "0",
        "id": "12345678-90ab-cdef-1234-567890abcdef",
        "detail-type": "WorkflowRunStateChange",
        "source": "orcabus.workflowmanager",
        "account": "000000000000",
        "time": "2025-03-00T00:00:00Z",
        "region": "ap-southeast-2",
        "resources": [],
        "detail": {
            "workflow": {
                "name": "bclconvert",
            },
            "payload": {
                "data": {
                    "tags": {
                        "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
                        "samplesheetChecksumType": "sha256",
                        ...
                    }
                "inputs": {
                    sampleSheetUri: "icav2://250328_A01052_0258_AHFGM7DSXF/sample_sheet.csv",
                    ...
                }
            }
        }
    }
    """
    logger.info(f"Received event: {event}")
    logger.info(f"Received context: {context}")
    logger.info(libjson.dumps(event))
    logger.info("Start processing sample sheet event ....")

    if event["detail-type"] == srssu.SequenceRunSampleSheetUpdate.__name__:
        srssu_event = srssu.AWSEvent.model_validate(event)
        sample_sheet_domain, library_linking_domain = (
            sample_sheet_srv.create_sequence_sample_sheet_from_srssu_event(
                srssu_event.detail
            )
        )

        # Detect SequenceRunSampleSheetChange and emit event
        if sample_sheet_domain and sample_sheet_domain.sample_sheet_has_changed:
            srssc_entry = sample_sheet_domain.to_put_events_request_entry(
                event_bus_name=os.environ["EVENT_BUS_NAME"],
            )
            libeb.emit_event(srssc_entry)
            logger.info(f"Emitted SequenceRunSampleSheetChange event: {srssc_entry}")

        # Detect SequenceRunLibraryLinkingChange and emit event
        if (
            library_linking_domain
            and library_linking_domain.library_linking_has_changed
        ):
            srllc_entry = library_linking_domain.to_put_events_request_entry(
                event_bus_name=os.environ["EVENT_BUS_NAME"],
            )
            libeb.emit_event(srllc_entry)
            logger.info(f"Emitted SequenceRunLibraryLinkingChange event: {srllc_entry}")
    elif event["detail-type"] == "WorkflowRunStateChange":
        sample_sheet_srv.validate_sample_sheet_from_wrsc_event(event["detail"])
    else:
        logger.error(f"Invalid event detail type: {event['detail-type']}")
        return {
            "message": f"Invalid event detail type: {event['detail-type']}",
        }
    return {
        "message": "Sample sheet event processed successfully",
    }
