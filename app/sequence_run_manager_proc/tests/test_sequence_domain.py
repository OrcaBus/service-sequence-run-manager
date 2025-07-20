import json
from datetime import datetime

from sequence_run_manager.tests.factories import SequenceFactory
from sequence_run_manager_proc.domain.sequence import SequenceDomain

from sequence_run_manager_proc.domain.events.srsc import SequenceRunStateChange, AWSEvent
from sequence_run_manager_proc.tests.case import SequenceRunProcUnitTestCase, logger


class SequenceDomainUnitTests(SequenceRunProcUnitTestCase):
    def setUp(self) -> None:
        super(SequenceDomainUnitTests, self).setUp()

    def tearDown(self) -> None:
        super(SequenceDomainUnitTests, self).tearDown()

    def test_marshall(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_marshall
        """
        mock_sequence = SequenceFactory()
        mock_sequence_domain = SequenceDomain(
            sequence=mock_sequence, state_has_changed=True, status_has_changed=True
        )

        event_json = mock_sequence_domain.to_event().model_dump_json()
        validated_object = SequenceRunStateChange.model_validate_json(event_json)

        logger.info(validated_object)
        logger.info(event_json)
        self.assertIsNotNone(validated_object)
        self.assertIsInstance(validated_object, SequenceRunStateChange)
        self.assertIn("id", validated_object.model_dump().keys())
        self.assertIn("instrumentRunId", validated_object.model_dump().keys())

    # def test_unmarshall(self):
    #     """
    #     python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_unmarshall
    #     """
    #     mock_sequence = SequenceFactory()
    #     mock_sequence_domain = SequenceDomain(
    #         sequence=mock_sequence, state_has_changed=True, status_has_changed=True
    #     )

    #     marshalled_object = SequenceRunStateChange.model_validate(mock_sequence_domain.to_event())

    #     unmarshalled_object = SequenceRunStateChange.model_validate(
    #         marshalled_object
    #     )

    #     logger.info(unmarshalled_object)
    #     self.assertIsNotNone(unmarshalled_object)
    #     self.assertIsInstance(unmarshalled_object, object)
    #     self.assertIsInstance(unmarshalled_object, SequenceRunStateChange)
    #     self.assertIsInstance(unmarshalled_object.startTime, datetime)

    def test_aws_event_serde(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_aws_event_serde
        """
        mock_sequence = SequenceFactory()
        mock_sequence_domain = SequenceDomain(
            sequence=mock_sequence, state_has_changed=True, status_has_changed=True
        )

        aws_event = mock_sequence_domain.to_event_with_envelope()

        logger.info(aws_event)
        logger.info(AWSEvent.model_validate_json(aws_event.model_dump_json()))
        self.assertIsNotNone(aws_event)
        self.assertIsInstance(aws_event, AWSEvent)

    def test_put_events_request_entry(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_domain.SequenceDomainUnitTests.test_put_events_request_entry
        """
        mock_sequence = SequenceFactory()
        mock_sequence_domain = SequenceDomain(
            sequence=mock_sequence, state_has_changed=True, status_has_changed=True
        )

        mock_entry = mock_sequence_domain.to_put_events_request_entry(
            event_bus_name="MockBus",
        )
        logger.info(mock_entry)
        mock_entry_detail = mock_entry["Detail"]

        self.assertIsNotNone(mock_entry)
        self.assertIsInstance(mock_entry, dict)
        self.assertIn("Detail", mock_entry.keys())
        self.assertIsInstance(mock_entry_detail, str)
        self.assertIsInstance(mock_entry["DetailType"], str)

        validated_detail = SequenceRunStateChange.model_validate_json(mock_entry_detail)
        self.assertIsInstance(validated_detail, SequenceRunStateChange)
