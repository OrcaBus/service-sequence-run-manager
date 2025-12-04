import logging
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from rest_framework.test import APIClient
import hashlib

from sequence_run_manager.models.sequence import Sequence, SequenceStatus, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment, TargetType
from sequence_run_manager.models.state import State

from sequence_run_manager.urls.base import api_base
from v2_samplesheet_parser.functions.parser import parse_samplesheet


logger = logging.getLogger()
logger.setLevel(logging.INFO)


class SequenceViewSetTestCase(TestCase):
    sequence_run_endpoint = f"/{api_base}sequence_run"
    sequence_endpoint = f"/{api_base}sequence"
    sample_sheet_endpoint = f"/{api_base}sample_sheet"

    def setUp(self):
        # Use DRF's APIClient for better compatibility with DRF viewsets
        self.client = APIClient()
        sequence = Sequence.objects.create(
            instrument_run_id="190101_A01052_0001_BH5LY7ACGT",
            run_volume_name="gds_name",
            run_folder_path="/to/gds/folder/path",
            run_data_uri="gds://gds_name/to/gds/folder/path",
            status=SequenceStatus.from_seq_run_status("Complete"),
            start_time=now(),
            sample_sheet_name="SampleSheet.csv",
            sequence_run_id="r.AAAAAA",
            sequence_run_name="190101_A01052_0001_BH5LY7ACGT",
            api_url="https://bssh.dev/api/v1/runs/r.AAAAAA",
            v1pre3_id="1234567890",
            ica_project_id="12345678-53ba-47a5-854d-e6b53101adb7",
            experiment_name="ExperimentName",
        )

        # read files from ./examples/standard-sheet-with-settings.csv
        with open(Path(__file__).parent / "examples/standard-sheet-with-settings.csv", "r") as f:
            samplesheet = f.read()
        sample_sheet_content = parse_samplesheet(samplesheet)
        SampleSheet.objects.create(
            sequence=sequence,
            sample_sheet_name="SampleSheet.csv",
            sample_sheet_content=sample_sheet_content,
            sample_sheet_content_original=samplesheet,  # Store original CSV content
        )
        Comment.objects.create(
            target_id=sequence.orcabus_id,
            target_type=TargetType.SEQUENCE,
            comment="TestComment",
            created_by="TestUser",
        )
        State.objects.create(
            sequence=sequence,
            status="Started",
            timestamp=now(),
        )
        State.objects.create(
            sequence=sequence,
            status="Complete",
            timestamp=now(),
        )
        LibraryAssociation.objects.create(
            sequence=sequence,
            library_id="LBR0001",
            association_date=now(),
            status="active",
        )

    def tearDown(self):
        Sequence.objects.all().delete()
        SampleSheet.objects.all().delete()
        Comment.objects.all().delete()
        State.objects.all().delete()
        LibraryAssociation.objects.all().delete()

    def test_get_sequence_runs(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_sequence_runs
        """
        # Get sequence list
        logger.info("Get sequence API")
        response = self.client.get(self.sequence_run_endpoint)
        self.assertEqual(response.status_code, 200, "Ok status response is expected")

        logger.info("Check if API return result")
        result_response = response.data["results"]
        self.assertEqual(len(result_response), 1, "At least one result is expected")

    def test_get_by_uk_surrogate_key(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_by_uk_surrogate_key
        """
        logger.info("Check if unique data has a single entry")
        response = self.client.get(f"{self.sequence_run_endpoint}/?instrument_run_id=190101_A01052_0001_BH5LY7ACGT")
        results_response = response.data["results"]
        self.assertEqual(
            len(results_response), 1, "Single result is expected for unique data"
        )

    def test_get_by_sequence_run_id(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_by_sequence_run_id
        """
        logger.info("Check if unique data has a single entry")
        response = self.client.get(f"{self.sequence_run_endpoint}/?sequence_run_id=r.AAAAAA")
        results_response = response.data["results"]
        self.assertEqual(
            len(results_response), 1, "Single result is expected for unique data"
        )

    def test_get_by_invalid_parameter(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_by_invalid_parameter
        """
        logger.info("Check if wrong parameter")
        response = self.client.get(f"{self.sequence_run_endpoint}/?lib_id=LBR0001")
        results_response = response.data["results"]
        self.assertEqual(
            len(results_response),
            0,
            "No results are expected for unrecognized query parameter",
        )
    def test_get_sequence_runs_by_instrument_run_id(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_sequence_runs_by_instrument_run_id
        """
        logger.info("Get sequence runs by instrument run id")
        instrument_run_id = "190101_A01052_0001_BH5LY7ACGT"
        response = self.client.get(f"{self.sequence_endpoint}/{instrument_run_id}/sequence_run/")
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertEqual(len(response.data), 1, "At least one result is expected")

    def test_get_sequence_states(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_sequence_states
        """
        logger.info("Get sequence states")
        instrument_run_id = "190101_A01052_0001_BH5LY7ACGT"
        response = self.client.get(f"{self.sequence_endpoint}/{instrument_run_id}/states/")
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertEqual(len(response.data), 2, "Two states are expected")

    # def test_add_sequence_run_comment(self):
    #     """
    #     python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_add_sequence_comment
    #     """
    #     logger.info("Add sequence comment")
    #     sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
    #     response = self.client.post(f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/", {
    #         "comment": "TestComment",
    #         "created_by": "TestUser001",
    #     })
    #     self.assertEqual(response.status_code, 200, "Ok status response is expected")
    #     self.assertEqual(response.data["comment"], "TestComment", "Comment is expected")
    #     self.assertEqual(response.data["created_by"], "TestUser001", "Created by is expected")

    def test_update_sequence_run_comment(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_update_sequence_run_comment
        """
        logger.info("Update sequence comment")
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE)
        # Note: created_by must match the original creator "TestUser" from setUp
        # APIClient uses format='json' instead of content_type
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            {
                "comment": "TestCommentUpdated",
                "created_by": "TestUser",  # Must match setUp
            },
            format='json'
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertEqual(response.data["comment"], "TestCommentUpdated", "Comment is expected")
        self.assertEqual(response.data["created_by"], "TestUser", "Created by is expected")

    def test_delete_sequence_run_comment(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_delete_sequence_run_comment
        """
        logger.info("Delete sequence comment")
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE)
        # Use the soft_delete action endpoint instead of direct DELETE
        # Note: created_by must match the original creator "TestUser" from setUp
        # APIClient uses format='json' instead of content_type
        response = self.client.delete(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/soft_delete/",
            {
                "created_by": "TestUser",  # Must match setUp
            },
            format='json'
        )
        self.assertEqual(response.status_code, 204, "No content status response is expected")
        self.assertEqual(Comment.objects.filter(orcabus_id=comment.orcabus_id, is_deleted=True).count(), 1, "Comment is expected to be deleted")

    @patch('sequence_run_manager.viewsets.sequence_run_action.emit_srm_api_event')
    def test_add_samplesheet_action(self, mock_emit_event):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_add_samplesheet_action
        """
        logger.info("Add samplesheet action")
        # Mock the event emission to avoid actual EventBridge calls
        mock_emit_event.return_value = None

        # Read the file content from ./examples/standard-sheet-with-settings.csv
        samplesheet_path = Path(__file__).parent / "examples/standard-sheet-with-settings.csv"
        with open(samplesheet_path, "rb") as f:
            samplesheet_content = f.read()

        # Create a SimpleUploadedFile object to mock the file upload
        uploaded_file = SimpleUploadedFile(
            name="standard-sheet-with-settings.csv",
            content=samplesheet_content,
            content_type="text/csv"
        )

        # POST request with file upload using DRF's APIClient
        # format='multipart' is required for file uploads with APIClient
        add_samplesheet_response = self.client.post(
            f"{self.sequence_run_endpoint}/action/add_samplesheet/",
            data={
                "instrument_run_id": "190101_A01052_0001_BH5LY7ACGT",
                'created_by': 'TestUser001',
                'comment': 'TestComment',
                'file': uploaded_file,  # Include file in data dict for multipart
            },
            format='multipart'
        )

        self.assertEqual(add_samplesheet_response.status_code, 200, f"Ok status response is expected, got {add_samplesheet_response.status_code}: {add_samplesheet_response.data}")
        self.assertEqual(add_samplesheet_response.data["detail"], "Samplesheet added successfully", "Detail is expected")

        # Get the created sequence_run (it's created by the add_samplesheet action)
        sequence_run = Sequence.objects.filter(
            instrument_run_id="190101_A01052_0001_BH5LY7ACGT"
        ).exclude(sequence_run_id="r.AAAAAA").first()
        self.assertIsNotNone(sequence_run, "Sequence run should be created by add_samplesheet action")

        # test get samplesheet
        get_samplesheet_response = self.client.get(f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/sample_sheet/")
        self.assertEqual(get_samplesheet_response.status_code, 200, f"Ok status response is expected, got {get_samplesheet_response.status_code}: {get_samplesheet_response.data}")
        self.assertEqual(get_samplesheet_response.data["sample_sheet_name"], "standard-sheet-with-settings.csv", "Sample sheet name is expected")
        self.assertEqual(get_samplesheet_response.data["sample_sheet_content_original"], samplesheet_content.decode('utf-8'), "Sample sheet content is expected")

        # test get samplesheet by ss orcabus_id
        ss_orcabus_id = get_samplesheet_response.data["orcabus_id"]
        get_samplesheet_response = self.client.get(f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/sample_sheet/{ss_orcabus_id}/")
        self.assertEqual(get_samplesheet_response.status_code, 200, f"Ok status response is expected, got {get_samplesheet_response.status_code}: {get_samplesheet_response.data}")
        self.assertEqual(get_samplesheet_response.data["sample_sheet_name"], "standard-sheet-with-settings.csv", "Sample sheet name is expected"),

        # test samplesheet api and cheksum query
        ss_orcabus_id = get_samplesheet_response.data["orcabus_id"]
        get_samplesheet_response = self.client.get(f"{self.sample_sheet_endpoint}/{ss_orcabus_id}/")
        self.assertEqual(get_samplesheet_response.status_code, 200, f"Ok status response is expected, got {get_samplesheet_response.status_code}: {get_samplesheet_response.data}")
        self.assertEqual(get_samplesheet_response.data["sample_sheet_name"], "standard-sheet-with-settings.csv", "Sample sheet name is expected")
        self.assertEqual(get_samplesheet_response.data["sample_sheet_content_original"], samplesheet_content.decode('utf-8'), "Sample sheet content is expected")

        # test samplesheet api and cheksum query checksum
        sample_sheet_content_original = get_samplesheet_response.data["sample_sheet_content_original"]
        ss_checksum = hashlib.sha256(sample_sheet_content_original.encode('utf-8')).hexdigest()
        get_samplesheet_checksum_response = self.client.get(f"{self.sample_sheet_endpoint}/?checksum={ss_checksum}&checksumType=sha256")
        self.assertEqual(get_samplesheet_checksum_response.status_code, 200, f"Ok status response is expected, got {get_samplesheet_checksum_response.status_code}: {get_samplesheet_checksum_response.data}")
        self.assertEqual(len(get_samplesheet_checksum_response.data), 2, "One result is expected")

        # test samplesheet api and cheksum query checksum by sequence run id
        get_samplesheet_checksum_response = self.client.get(f"{self.sample_sheet_endpoint}/?sequenceRunId=r.AAAAAA")
        self.assertEqual(get_samplesheet_checksum_response.status_code, 200, f"Ok status response is expected, got {get_samplesheet_checksum_response.status_code}: {get_samplesheet_checksum_response.data}")
        self.assertEqual(len(get_samplesheet_checksum_response.data), 1, "One result is expected")
