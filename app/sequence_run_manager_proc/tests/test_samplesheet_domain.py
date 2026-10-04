from django.utils.timezone import now

from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager_proc.domain.events.srssc import (
    AWSEvent,
    SequenceRunSampleSheetChange,
)
from sequence_run_manager_proc.domain.samplesheet import (
    SRSSC_SCHEMA_VERSION,
    SampleSheetDomain,
    get_srssc_hash,
)
from sequence_run_manager_proc.tests.case import SequenceRunProcUnitTestCase


class SampleSheetDomainUnitTests(SequenceRunProcUnitTestCase):
    def build_domain(self) -> SampleSheetDomain:
        sample_sheet = SampleSheet(
            orcabus_id="ss.01J5M2JFE1JPYV62RYQEG99SS",
            sample_sheet_name="SampleSheet.csv",
            sample_sheet_content_original="sample,sheet\n",
            association_timestamp=now(),
        )
        return SampleSheetDomain(
            instrument_run_id="250328_A01052_0258_AHFGM7DSXF",
            sequence_run_id="r.01J5M2JFE1JPYV62RYQEG99RUN",
            sample_sheet=sample_sheet,
            description="Sample sheet added",
            sample_sheet_has_changed=True,
        )

    def test_event_is_versioned_and_hashed(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_domain.SampleSheetDomainUnitTests.test_event_is_versioned_and_hashed
        """
        event = self.build_domain().to_event()

        self.assertEqual(event.version, SRSSC_SCHEMA_VERSION)
        self.assertRegex(event.id, r"^[0-9a-f]{32}$")
        self.assertEqual(event.id, get_srssc_hash(event.model_copy(update={"id": ""})))

    def test_put_events_request_entry(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_domain.SampleSheetDomainUnitTests.test_put_events_request_entry
        """
        entry = self.build_domain().to_put_events_request_entry(
            event_bus_name="MockBus"
        )

        self.assertEqual(entry["DetailType"], "SequenceRunSampleSheetChange")
        self.assertEqual(entry["Source"], "orcabus.sequencerunmanager")
        detail = SequenceRunSampleSheetChange.model_validate_json(entry["Detail"])
        self.assertEqual(detail.version, SRSSC_SCHEMA_VERSION)
        self.assertEqual(
            detail.id, get_srssc_hash(detail.model_copy(update={"id": ""}))
        )

    def test_aws_event_serde(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_domain.SampleSheetDomainUnitTests.test_aws_event_serde
        """
        aws_event = self.build_domain().to_event_with_envelope()

        self.assertIsInstance(
            AWSEvent.model_validate_json(aws_event.model_dump_json()), AWSEvent
        )
        # a raw EventBridge event carries the `detail-type` alias
        self.assertIsInstance(
            AWSEvent.model_validate(aws_event.model_dump(mode="json", by_alias=True)),
            AWSEvent,
        )


class SrsscHashUnitTests(SequenceRunProcUnitTestCase):
    """Content hashing of SequenceRunSampleSheetChange events (schema 1.1.0)."""

    def build_srssc(self, **overrides) -> SequenceRunSampleSheetChange:
        fields = {
            "id": "",
            "version": SRSSC_SCHEMA_VERSION,
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "sequenceRunId": "r.01J5M2JFE1JPYV62RYQEG99RUN",
            "timeStamp": now(),
            "sampleSheetName": "SampleSheet.csv",
            "apiUrl": "https://srm.example/api/v1/sample_sheet/ss.01J5M2JFE1JPYV62RYQEG99SS/",
            "checksum": "a" * 64,
            "checksumType": "sha256",
            "description": "Sample sheet added",
        }
        fields.update(overrides)
        return SequenceRunSampleSheetChange(**fields)

    def test_hash_is_stable_and_idempotent(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_domain.SrsscHashUnitTests.test_hash_is_stable_and_idempotent
        """
        first = get_srssc_hash(self.build_srssc())
        # Neither a later timestamp nor another description change the hash.
        second = get_srssc_hash(
            self.build_srssc(timeStamp=now(), description="Sample sheet re-announced")
        )
        self.assertEqual(first, second)

        # An event that already carries an id keeps it.
        self.assertEqual(get_srssc_hash(self.build_srssc(id=first)), first)

    def test_hash_differs_by_sample_sheet(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_domain.SrsscHashUnitTests.test_hash_differs_by_sample_sheet
        """
        base = get_srssc_hash(self.build_srssc())
        for overrides in (
            {"version": "9.9.9"},
            {"sequenceRunId": "r.01J5M2JFE1JPYV62RYQEG99OTHER"},
            {"sampleSheetName": "SampleSheet_v2.csv"},
            {"apiUrl": "https://srm.example/api/v1/sample_sheet/ss.OTHER/"},
            {"checksum": "b" * 64},
        ):
            with self.subTest(**overrides):
                self.assertNotEqual(base, get_srssc_hash(self.build_srssc(**overrides)))
