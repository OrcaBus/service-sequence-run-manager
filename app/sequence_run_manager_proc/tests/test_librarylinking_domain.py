from django.utils.timezone import now

from sequence_run_manager_proc.domain.events.srllc import (
    AWSEvent,
    SequenceRunLibraryLinkingChange,
)
from sequence_run_manager_proc.domain.librarylinking import (
    SRLLC_SCHEMA_VERSION,
    LibraryLinkingDomain,
    get_srllc_hash,
)
from sequence_run_manager_proc.tests.case import SequenceRunProcUnitTestCase


class LibraryLinkingDomainUnitTests(SequenceRunProcUnitTestCase):
    def build_domain(self) -> LibraryLinkingDomain:
        return LibraryLinkingDomain(
            instrument_run_id="250328_A01052_0258_AHFGM7DSXF",
            sequence_run_id="r.01J5M2JFE1JPYV62RYQEG99RUN",
            linked_libraries=["L2000001", "L2000002"],
            timestamp=now(),
            library_linking_has_changed=True,
        )

    def test_event_is_versioned_and_hashed(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_domain.LibraryLinkingDomainUnitTests.test_event_is_versioned_and_hashed
        """
        event = self.build_domain().to_event()

        self.assertEqual(event.version, SRLLC_SCHEMA_VERSION)
        self.assertRegex(event.id, r"^[0-9a-f]{32}$")
        self.assertEqual(event.id, get_srllc_hash(event.model_copy(update={"id": ""})))

    def test_put_events_request_entry(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_domain.LibraryLinkingDomainUnitTests.test_put_events_request_entry
        """
        entry = self.build_domain().to_put_events_request_entry(
            event_bus_name="MockBus"
        )

        self.assertEqual(entry["DetailType"], "SequenceRunLibraryLinkingChange")
        self.assertEqual(entry["Source"], "orcabus.sequencerunmanager")
        detail = SequenceRunLibraryLinkingChange.model_validate_json(entry["Detail"])
        self.assertEqual(detail.version, SRLLC_SCHEMA_VERSION)
        self.assertEqual(
            detail.id, get_srllc_hash(detail.model_copy(update={"id": ""}))
        )

    def test_aws_event_serde(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_domain.LibraryLinkingDomainUnitTests.test_aws_event_serde
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


class SrllcHashUnitTests(SequenceRunProcUnitTestCase):
    """Content hashing of SequenceRunLibraryLinkingChange events (schema 1.1.0)."""

    def build_srllc(self, **overrides) -> SequenceRunLibraryLinkingChange:
        fields = {
            "id": "",
            "version": SRLLC_SCHEMA_VERSION,
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "sequenceRunId": "r.01J5M2JFE1JPYV62RYQEG99RUN",
            "timeStamp": now(),
            "linkedLibraries": ["L2000001", "L2000002"],
        }
        fields.update(overrides)
        return SequenceRunLibraryLinkingChange(**fields)

    def test_hash_is_stable_and_idempotent(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_domain.SrllcHashUnitTests.test_hash_is_stable_and_idempotent
        """
        first = get_srllc_hash(self.build_srllc())
        # A later timestamp must not change the hash: only content does.
        self.assertEqual(first, get_srllc_hash(self.build_srllc(timeStamp=now())))

        # The linking is a set, so neither order nor repeats matter.
        reordered = self.build_srllc(
            linkedLibraries=["L2000002", "L2000001", "L2000001"]
        )
        self.assertEqual(first, get_srllc_hash(reordered))

        # An event that already carries an id keeps it.
        self.assertEqual(get_srllc_hash(self.build_srllc(id=first)), first)

    def test_hash_differs_by_linking(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_domain.SrllcHashUnitTests.test_hash_differs_by_linking
        """
        base = get_srllc_hash(self.build_srllc())
        for overrides in (
            {"version": "9.9.9"},
            {"sequenceRunId": "r.01J5M2JFE1JPYV62RYQEG99OTHER"},
            {"linkedLibraries": ["L2000001"]},
            {"linkedLibraries": ["L2000001", "L2000002", "L2000003"]},
        ):
            with self.subTest(**overrides):
                self.assertNotEqual(base, get_srllc_hash(self.build_srllc(**overrides)))
