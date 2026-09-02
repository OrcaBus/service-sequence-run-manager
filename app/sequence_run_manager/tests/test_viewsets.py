import logging
from pathlib import Path
from threading import Barrier, Thread
from unittest.mock import Mock, patch
import base64
import json

from django.db import DatabaseError, close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from datetime import timedelta
from rest_framework.test import APIClient
import hashlib

from sequence_run_manager.models.sequence import (
    Sequence,
    SequenceStatus,
    LibraryAssociation,
)
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment, TargetType
from sequence_run_manager.models.state import State

from sequence_run_manager.urls.base import api_base
from sequence_run_manager.viewsets.state import StateTransitionMixin
from sequence_run_manager_proc.domain.events.srsc import SequenceRunStateChange
from sequence_run_manager_proc.services.sequence_state_srv import get_srsc_hash
from v2_samplesheet_parser.functions.parser import parse_samplesheet

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_srsc_hash_for(srsc_event: dict) -> str:
    """Recompute an SRSC event id from its detail, mirroring the emitter."""
    return get_srsc_hash(SequenceRunStateChange.model_validate(srsc_event))


def _make_bearer_token(email: str) -> str:
    """Minimal RS256-shaped JWT (payload only used; signature not verified by the API)."""

    def _b64url(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return ".".join(
        [
            _b64url({"alg": "RS256", "typ": "JWT"}),
            _b64url({"email": email}),
            _b64url({"sig": "test"}),
        ]
    )


class SequenceViewSetTestCase(TestCase):
    sequence_run_endpoint = f"/{api_base}sequence_run"
    state_transition_endpoint = f"/{api_base}sequence_run/state"
    state_actor_email = "State.Actor@example.org"
    sequence_endpoint = f"/{api_base}sequence"
    sample_sheet_endpoint = f"/{api_base}sample_sheet"
    stats_sequence_run_status_counts_endpoint = (
        f"/{api_base}stats/sequence_run_status_counts"
    )
    stats_instrument_run_status_counts_endpoint = (
        f"/{api_base}stats/instrument_run_status_counts"
    )

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
        with open(
            Path(__file__).parent / "examples/standard-sheet-with-settings.csv", "r"
        ) as f:
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
        # Explicit ordering so get_latest_state() is deterministic (newest timestamp wins).
        State.objects.create(
            sequence=sequence,
            status="Started",
            timestamp=now() - timedelta(seconds=2),
        )
        State.objects.create(
            sequence=sequence,
            status="Complete",
            timestamp=now() - timedelta(seconds=1),
        )
        LibraryAssociation.objects.create(
            sequence=sequence,
            library_id="LBR0001",
            association_date=now(),
            status="active",
        )

    def authenticate_state_actor(self, email=None) -> str:
        """Present a Bearer JWT on the client and return the email it records."""
        email = email or self.state_actor_email
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_make_bearer_token(email)}"
        )
        return email.strip().lower()

    def tearDown(self):
        self.client.credentials()
        Sequence.objects.all().delete()
        SampleSheet.objects.all().delete()
        Comment.objects.all().delete()
        State.objects.all().delete()
        LibraryAssociation.objects.all().delete()

    def test_list_status_filters_sequence_row_group_status_filters_latest_in_group(
        self,
    ):
        """
        ``GET /sequence_run/?status=`` filters ``Sequence.status`` per row.
        ``list_by_instrument_run_id`` uses ``status`` against the group's latest-by-start_time status.
        """
        instrument_run_id = "190101_A01052_0001_BH5LY7ACGT"
        Sequence.objects.create(
            instrument_run_id=instrument_run_id,
            run_volume_name="gds_name",
            run_folder_path="/to/gds/folder/path",
            run_data_uri="gds://gds_name/to/gds/folder/path",
            status=SequenceStatus.STARTED,
            start_time=now() - timedelta(days=1),
            sample_sheet_name="SampleSheet.csv",
            sequence_run_id="r.OLDER",
            sequence_run_name=instrument_run_id,
            api_url="https://bssh.dev/api/v1/runs/r.OLDER",
            v1pre3_id="1234567890",
            ica_project_id="12345678-53ba-47a5-854d-e6b53101adb7",
            experiment_name="ExperimentName",
        )

        list_started = self.client.get(f"{self.sequence_run_endpoint}/?status=STARTED")
        self.assertEqual(list_started.status_code, 200)
        self.assertEqual(len(list_started.data["results"]), 1)
        self.assertEqual(list_started.data["results"][0]["sequence_run_id"], "r.OLDER")

        grouped = self.client.get(
            f"{self.sequence_run_endpoint}/list_by_instrument_run_id/?status=STARTED"
        )
        self.assertEqual(grouped.status_code, 200)
        self.assertEqual(len(grouped.data.get("results", [])), 0)

        grouped_succ = self.client.get(
            f"{self.sequence_run_endpoint}/list_by_instrument_run_id/?status=SUCCEEDED"
        )
        self.assertEqual(grouped_succ.status_code, 200)
        self.assertEqual(len(grouped_succ.data.get("results", [])), 1)
        self.assertEqual(grouped_succ.data["results"][0]["status"], "SUCCEEDED")

    def test_stats_sequence_run_status_counts_endpoint(self):
        """Smoke: per-sequence status totals under ``/stats/sequence_run_status_counts/``."""
        r = self.client.get(self.stats_sequence_run_status_counts_endpoint)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.data.get("all", 0), 1)

    def test_instrument_run_status_counts_endpoint(self):
        r = self.client.get(self.stats_instrument_run_status_counts_endpoint)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.data.get("all", 0), 1)

    def test_instrument_run_status_counts_one_per_group(self):
        """
        Regression: ``succeeded`` (etc.) must count **instrument runs**, not sequence rows.
        One group with two sequences and latest status SUCCEEDED must contribute 1 to succeeded.
        """
        Sequence.objects.all().delete()
        ir = "MULTI_SEQ_SAME_INSTR"
        base = dict(
            run_volume_name="gds",
            run_folder_path="/p",
            run_data_uri="gds://gds/p",
            sample_sheet_name="SampleSheet.csv",
            instrument_run_id=ir,
            api_url="https://bssh.dev/api/v1/runs/x",
            v1pre3_id="1",
            ica_project_id="12345678-53ba-47a5-854d-e6b53101adb7",
            experiment_name="Exp",
        )
        Sequence.objects.create(
            **base,
            status=SequenceStatus.FAILED,
            start_time=now() - timedelta(hours=2),
            sequence_run_id="r.failmulti",
            sequence_run_name=ir,
        )
        Sequence.objects.create(
            **base,
            status=SequenceStatus.SUCCEEDED,
            start_time=now() - timedelta(hours=1),
            sequence_run_id="r.succmulti",
            sequence_run_name=ir,
        )
        r = self.client.get(self.stats_instrument_run_status_counts_endpoint)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("all"), 1)
        self.assertEqual(r.data.get("succeeded"), 1)
        self.assertEqual(r.data.get("failed"), 0)

    def test_stats_sequence_run_status_counts_matches_list_start_time_filter(self):
        """
        ``sequence_run_status_counts`` must apply the same ``start_time`` (gte) semantics as the list API
        when only ``start_time`` is provided (not both bounds).
        """
        empty = self.client.get(
            f"{self.stats_sequence_run_status_counts_endpoint}?start_time=2099-01-01T00:00:00%2B00:00"
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data.get("all"), 0)

        hit = self.client.get(
            f"{self.stats_sequence_run_status_counts_endpoint}?start_time=2020-01-01T00:00:00%2B00:00"
        )
        self.assertEqual(hit.status_code, 200)
        self.assertGreaterEqual(hit.data.get("all", 0), 1)

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
        response = self.client.get(
            f"{self.sequence_run_endpoint}/?instrument_run_id=190101_A01052_0001_BH5LY7ACGT"
        )
        results_response = response.data["results"]
        self.assertEqual(
            len(results_response), 1, "Single result is expected for unique data"
        )

    def test_get_by_sequence_run_id(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_by_sequence_run_id
        """
        logger.info("Check if unique data has a single entry")
        response = self.client.get(
            f"{self.sequence_run_endpoint}/?sequence_run_id=r.AAAAAA"
        )
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
        response = self.client.get(
            f"{self.sequence_endpoint}/{instrument_run_id}/sequence_run/"
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertEqual(len(response.data), 1, "At least one result is expected")

    def test_get_sequence_states(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_sequence_states
        """
        logger.info("Get sequence states")
        instrument_run_id = "190101_A01052_0001_BH5LY7ACGT"
        response = self.client.get(
            f"{self.sequence_endpoint}/{instrument_run_id}/states/"
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertEqual(len(response.data), 2, "Two states are expected")

    def test_get_sequence_comments_excludes_soft_deleted_comments(self):
        instrument_run_id = "190101_A01052_0001_BH5LY7ACGT"
        sequence = Sequence.objects.get(instrument_run_id=instrument_run_id)
        active_comment = Comment.objects.get(
            target_id=sequence.orcabus_id, target_type=TargetType.SEQUENCE
        )
        deleted_comment = Comment.objects.create(
            target_id=sequence.orcabus_id,
            target_type=TargetType.SEQUENCE,
            comment="Deleted comment",
            created_by="TestUser",
            is_deleted=True,
        )

        response = self.client.get(
            f"{self.sequence_endpoint}/{instrument_run_id}/comments/"
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {comment["orcabus_id"] for comment in response.data}
        self.assertIn(str(active_comment.orcabus_id), returned_ids)
        self.assertNotIn(str(deleted_comment.orcabus_id), returned_ids)

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
        comment = Comment.objects.get(
            target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE
        )
        # Authorisation via body `created_by` matching the stored author (case-insensitive in the view).
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            {
                "comment": "TestCommentUpdated",
                "created_by": "TestUser",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, "Ok status response is expected")
        self.assertEqual(
            response.data["comment"], "TestCommentUpdated", "Comment is expected"
        )
        self.assertEqual(
            response.data["created_by"], "TestUser", "Created by is expected"
        )

    def test_update_sequence_run_comment_via_bearer_email(self):
        """
        PATCH with only `comment`; actor email comes from Authorization Bearer JWT claim.
        """
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(
            target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_make_bearer_token('TestUser')}"
        )
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            {"comment": "BearerUpdated"},
            format="json",
        )
        self.client.credentials()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["comment"], "BearerUpdated")

    def test_update_sequence_run_comment_requires_bearer_when_created_by_omitted(self):
        """Without `created_by` in the body, the view requires a Bearer token with an email claim."""
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(
            target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE
        )
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            {"comment": "NoAuth"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_update_sequence_run_comment_permission_denied_wrong_bearer_email(self):
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(
            target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_make_bearer_token('someone.else@example.com')}"
        )
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            {"comment": "Hijack"},
            format="json",
        )
        self.client.credentials()
        self.assertEqual(response.status_code, 403)

    def test_update_sequence_run_comment_permission_denied_wrong_created_by(self):
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(
            target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE
        )
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            {"comment": "Nope", "created_by": "NotTheAuthor"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_sequence_run_comment(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_delete_sequence_run_comment
        """
        logger.info("Delete sequence comment")
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        comment = Comment.objects.get(
            target_id=sequence_run.orcabus_id, target_type=TargetType.SEQUENCE
        )

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_make_bearer_token('TestUser')}"
        )

        response = self.client.delete(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/comment/{comment.orcabus_id}/",
            format="json",
        )
        self.assertEqual(
            response.status_code, 204, "No content status response is expected"
        )
        self.assertEqual(
            Comment.objects.filter(
                orcabus_id=comment.orcabus_id, is_deleted=True
            ).count(),
            1,
            "Comment is expected to be deleted",
        )
        self.client.credentials()

    def test_get_states_transition_validation_map(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_states_transition_validation_map
        """
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        response = self.client.get(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/get_states_transition_validation_map/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"RESOLVED": ["FAILED"], "DEPRECATED": ["SUCCEEDED"]},
        )

    def test_get_states_transition_validation_map_on_transition_endpoint(self):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_get_states_transition_validation_map_on_transition_endpoint
        """
        response = self.client.get(
            f"{self.state_transition_endpoint}/get_states_transition_validation_map/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"RESOLVED": ["FAILED"], "DEPRECATED": ["SUCCEEDED"]},
        )

    def test_state_transition_mixin_validation_rules(self):
        actor = self.authenticate_state_actor()
        mixin = StateTransitionMixin()

        self.assertTrue(mixin.is_valid_next_state(None, "DEPRECATED"))
        self.assertFalse(mixin.is_valid_next_state(None, "RESOLVED"))
        self.assertFalse(mixin.is_valid_next_state("FAILED", "UNKNOWN"))
        self.assertTrue(mixin._validate_state_status("FAILED", "RESOLVED"))

        mixin.states_transition_validation_map = {
            "DEPRECATED": {
                "excluded_states": ["FAILED", "ABORTED", "RESOLVED", "DEPRECATED"]
            },
            "RESOLVED": {"allowed_states": ["FAILED"]},
            "IGNORED": "unsupported-rule",
        }

        self.assertTrue(mixin.is_valid_next_state("SUCCEEDED", "DEPRECATED"))
        self.assertFalse(mixin.is_valid_next_state("FAILED", "DEPRECATED"))
        self.assertTrue(mixin.is_valid_next_state("FAILED", "RESOLVED"))
        self.assertFalse(mixin.is_valid_next_state("SUCCEEDED", "RESOLVED"))
        self.assertFalse(mixin.is_valid_next_state("FAILED", "IGNORED"))

    def custom_state(self, sequence_run, created_by=None, status="RESOLVED"):
        """A user-created state, the only kind whose comment can be edited."""
        return State.objects.create(
            sequence=sequence_run,
            status=status,
            timestamp=now(),
            comment="Original note",
            created_by=created_by,
        )

    def test_patch_state_comment(self):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by=actor)
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {"comment": "Resolution note"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["comment"], "Resolution note")
        self.assertEqual(response.data["created_by"], actor)
        state.refresh_from_db()
        self.assertEqual(state.comment, "Resolution note")

    @patch("sequence_run_manager.viewsets.state.StateViewSet.get_object")
    def test_patch_state_comment_clears_prefetch_cache(self, mock_get_object):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by=actor)
        original_save = state.save

        def save_with_prefetch_cache(*args, **kwargs):
            result = original_save(*args, **kwargs)
            state._prefetched_objects_cache = {"cached": ["value"]}
            return result

        state.save = save_with_prefetch_cache
        mock_get_object.return_value = state

        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {"comment": "Resolution note"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state._prefetched_objects_cache, {})

    def test_patch_state_requires_comment(self):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by=actor)
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("comment", response.data.get("detail", "").lower())

    def test_patch_state_requires_bearer_token(self):
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by="someone@example.org")
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {"comment": "Resolution note"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        state.refresh_from_db()
        self.assertEqual(state.comment, "Original note")

    def test_patch_state_rejects_system_generated_state(self):
        """Only RESOLVED/DEPRECATED states carry an editable comment."""
        self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        system_state = (
            State.objects.filter(sequence=sequence_run).order_by("-timestamp").first()
        )
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{system_state.orcabus_id}/",
            {"comment": "Resolution note"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"], "Invalid state status to update comment."
        )

    def test_patch_state_rejects_non_creator(self):
        self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by="someone.else@example.org")
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {"comment": "Not mine to edit"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        state.refresh_from_db()
        self.assertEqual(state.comment, "Original note")

    def test_patch_state_creator_match_is_case_insensitive(self):
        self.authenticate_state_actor("STATE.ACTOR@EXAMPLE.ORG")
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by="state.actor@example.org")
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {"comment": "Resolution note"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_patch_state_without_creator_is_editable_by_any_authenticated_user(self):
        """Legacy states predate creator auditing; no ownership is inferred."""
        self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        legacy_state = self.custom_state(sequence_run, created_by=None)
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{legacy_state.orcabus_id}/",
            {"comment": "Adopted note"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        legacy_state.refresh_from_db()
        self.assertEqual(legacy_state.comment, "Adopted note")
        self.assertIsNone(legacy_state.created_by)

    def test_patch_state_ignores_client_supplied_created_by(self):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        state = self.custom_state(sequence_run, created_by=actor)
        response = self.client.patch(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/{state.orcabus_id}/",
            {"comment": "Resolution note", "createdBy": "impostor@example.org"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        state.refresh_from_db()
        self.assertEqual(state.created_by, actor)

    def test_state_transition_requires_ids_and_comment(self):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        missing_comment = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {"sequenceRunOrcabusIds": [sequence_run.orcabus_id]},
            format="json",
        )
        self.assertEqual(missing_comment.status_code, 400)
        self.assertIn("comment", missing_comment.data)

        missing_ids = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {"comment": "Handled"},
            format="json",
        )
        self.assertEqual(missing_ids.status_code, 400)
        self.assertIn("sequence_run_orcabus_ids", missing_ids.data)

    def test_state_transition_requires_bearer_token(self):
        """Authorship comes from the JWT, so an unauthenticated batch is rejected."""
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])

        response = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {
                "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                "comment": "Handled",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            State.objects.filter(sequence=sequence_run, status="RESOLVED").exists()
        )
        sequence_run.refresh_from_db()
        self.assertEqual(sequence_run.status, "FAILED")

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_ignores_client_supplied_created_by(
        self, mock_emit_srsc_event
    ):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{self.state_transition_endpoint}/resolve/",
                {
                    "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                    "comment": "Handled",
                    "createdBy": "impostor@example.org",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        state = State.objects.get(sequence=sequence_run, status="RESOLVED")
        self.assertEqual(state.created_by, actor)
        srsc_event = mock_emit_srsc_event.call_args.args[0]
        self.assertEqual(srsc_event["stateCreatedBy"], actor)

    def test_state_transition_post_to_state_list_is_not_allowed(self):
        """The generic POST /state/ endpoint is replaced by the dedicated transitions."""
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        response = self.client.post(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/state/",
            {"status": "RESOLVED", "comment": "Handled"},
            format="json",
        )
        self.assertEqual(response.status_code, 405)

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_sequence_run_not_found(self, mock_emit_srsc_event):
        actor = self.authenticate_state_actor()
        response = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {
                "sequenceRunOrcabusIds": ["seq.01J5M2J44HFJ9424G7074NKTGN"],
                "comment": "Handled",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["created_count"], 0)
        self.assertEqual(response.data["failed_count"], 1)
        self.assertEqual(response.data["failures"][0]["reason"], "NOT_FOUND")
        mock_emit_srsc_event.assert_not_called()

    def test_state_transition_invalid_transition(self):
        """Sequence status wins even when the latest state allows the transition."""
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        State.objects.create(
            sequence=sequence_run,
            status="FAILED",
            timestamp=now(),
            comment="failed",
        )
        response = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {
                "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                "comment": "Cannot from SUCCEEDED",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["created_count"], 0)
        self.assertEqual(response.data["failures"][0]["reason"], "INVALID_TRANSITION")
        self.assertFalse(
            State.objects.filter(sequence=sequence_run, status="RESOLVED").exists()
        )

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_revalidates_locked_sequence_status(
        self, mock_emit_srsc_event
    ):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])

        locked_sequence = Sequence.objects.get(pk=sequence_run.pk)
        locked_sequence.status = SequenceStatus.RESOLVED
        locked_queryset = Mock()
        locked_queryset.get.return_value = locked_sequence

        with patch.object(
            Sequence.objects,
            "select_for_update",
            return_value=locked_queryset,
        ) as mock_select_for_update:
            with self.assertLogs(
                "sequence_run_manager.viewsets.state", level="WARNING"
            ) as logs:
                response = self.client.post(
                    f"{self.state_transition_endpoint}/resolve/",
                    {
                        "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                        "comment": "Handled",
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["failures"][0]["reason"], "INVALID_TRANSITION")
        self.assertIn("concurrent_update=true", " ".join(logs.output))
        self.assertFalse(
            State.objects.filter(sequence=sequence_run, status="RESOLVED").exists()
        )
        mock_select_for_update.assert_called_once_with()
        mock_emit_srsc_event.assert_not_called()

    @patch(
        "sequence_run_manager.viewsets.state.SequenceRunStateTransitionViewSet.create_state_and_build_srsc",
        side_effect=DatabaseError("database unavailable"),
    )
    def test_state_transition_database_failure_returns_error_and_rolls_back_state(
        self, mock_create_state_and_build_srsc
    ):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])
        State.objects.create(
            sequence=sequence_run,
            status="FAILED",
            timestamp=now(),
            comment="failed",
        )

        response = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {
                "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                "comment": "Handled",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["created_count"], 0)
        failure = response.data["failures"][0]
        self.assertEqual(failure["reason"], "STATE_CREATION_FAILED")
        self.assertIn("rolled back", failure["detail"])
        self.assertFalse(
            State.objects.filter(sequence=sequence_run, status="RESOLVED").exists()
        )
        mock_create_state_and_build_srsc.assert_called_once()

    @patch(
        "sequence_run_manager.viewsets.state.SequenceRunStateTransitionViewSet.create_state_and_build_srsc",
        side_effect=RuntimeError("unexpected boom"),
    )
    def test_state_transition_unexpected_failure_returns_error_and_rolls_back_state(
        self, mock_create_state_and_build_srsc
    ):
        """A non-DatabaseError raised before commit is reported, not propagated."""
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])
        State.objects.create(
            sequence=sequence_run,
            status="FAILED",
            timestamp=now(),
            comment="failed",
        )

        with self.assertLogs(
            "sequence_run_manager.viewsets.state", level="ERROR"
        ) as logs:
            response = self.client.post(
                f"{self.state_transition_endpoint}/resolve/",
                {
                    "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                    "comment": "Handled",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["created_count"], 0)
        failure = response.data["failures"][0]
        self.assertEqual(failure["reason"], "STATE_CREATION_FAILED")
        self.assertIn("rolled back", failure["detail"])
        self.assertIn("rolled back", " ".join(logs.output))
        self.assertFalse(
            State.objects.filter(sequence=sequence_run, status="RESOLVED").exists()
        )
        sequence_run.refresh_from_db()
        self.assertEqual(sequence_run.status, SequenceStatus.FAILED)
        mock_create_state_and_build_srsc.assert_called_once()

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_accepts_orcabus_id_without_seq_prefix(
        self, mock_emit_srsc_event
    ):
        """Ids are accepted both with and without the ``seq.`` prefix."""
        self.assertEqual(
            StateTransitionMixin.normalize_sequence_run_orcabus_id(
                "01J5M2J44HFJ9424G7074NKTGN"
            ),
            "01J5M2J44HFJ9424G7074NKTGN",
        )

        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])
        unprefixed_id = StateTransitionMixin.normalize_sequence_run_orcabus_id(
            sequence_run.orcabus_id
        )
        self.assertNotEqual(unprefixed_id, sequence_run.orcabus_id)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{self.state_transition_endpoint}/resolve/",
                {
                    "sequenceRunOrcabusIds": [unprefixed_id],
                    "comment": "Handled",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_count"], 1)
        self.assertTrue(
            State.objects.filter(sequence=sequence_run, status="RESOLVED").exists()
        )
        mock_emit_srsc_event.assert_called_once()

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_resolve_after_failed(self, mock_emit_srsc_event):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])
        State.objects.create(
            sequence=sequence_run,
            status="SUCCEEDED",
            timestamp=now(),
            comment="stale detail status",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{self.state_transition_endpoint}/resolve/",
                {
                    "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                    "comment": "Handled",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_count"], 1)
        self.assertEqual(response.data["failed_count"], 0)
        self.assertEqual(
            response.data["sequence_run_orcabus_ids"], [sequence_run.orcabus_id]
        )
        state = State.objects.get(sequence=sequence_run, status="RESOLVED")
        self.assertEqual(state.comment, "Handled")
        sequence_run.refresh_from_db()
        self.assertEqual(
            sequence_run.status,
            "RESOLVED",
            "Sequence status should be updated to RESOLVED",
        )
        mock_emit_srsc_event.assert_called_once()
        srsc_event = mock_emit_srsc_event.call_args.args[0]
        self.assertEqual(srsc_event["version"], "1.1.0")
        self.assertEqual(srsc_event["orcabusId"], sequence_run.orcabus_id)
        self.assertEqual(srsc_event["stateCreatedBy"], actor)
        self.assertEqual(state.created_by, actor)
        # `id` is a content hash of the event, no longer the sequence id.
        self.assertNotEqual(srsc_event["id"], sequence_run.orcabus_id)
        self.assertEqual(srsc_event["id"], get_srsc_hash_for(srsc_event))
        self.assertEqual(srsc_event["instrumentRunId"], sequence_run.instrument_run_id)
        self.assertEqual(srsc_event["runVolumeName"], sequence_run.run_volume_name)
        self.assertEqual(srsc_event["runFolderPath"], sequence_run.run_folder_path)
        self.assertEqual(srsc_event["runDataUri"], sequence_run.run_data_uri)
        self.assertEqual(srsc_event["sampleSheetName"], sequence_run.sample_sheet_name)
        self.assertEqual(srsc_event["status"], "RESOLVED")

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_deprecate_after_succeeded(self, mock_emit_srsc_event):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        State.objects.create(
            sequence=sequence_run,
            status="FAILED",
            timestamp=now(),
            comment="stale detail status",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{self.state_transition_endpoint}/deprecate/",
                {
                    "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                    "comment": "No longer used",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_count"], 1)
        self.assertTrue(
            State.objects.filter(sequence=sequence_run, status="DEPRECATED").exists()
        )
        sequence_run.refresh_from_db()
        self.assertEqual(
            sequence_run.status,
            "DEPRECATED",
            "Sequence status should be updated to DEPRECATED",
        )
        mock_emit_srsc_event.assert_called_once()
        srsc_event = mock_emit_srsc_event.call_args.args[0]
        self.assertEqual(srsc_event["orcabusId"], sequence_run.orcabus_id)
        self.assertEqual(srsc_event["status"], "DEPRECATED")
        self.assertEqual(srsc_event["stateCreatedBy"], actor)

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_partial_success_returns_207(self, mock_emit_srsc_event):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{self.state_transition_endpoint}/resolve/",
                {
                    "sequenceRunOrcabusIds": [
                        sequence_run.orcabus_id,
                        "seq.01J5M2J44HFJ9424G7074NKTGN",
                    ],
                    "comment": "Handled",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.data["created_count"], 1)
        self.assertEqual(
            response.data["sequence_run_orcabus_ids"], [sequence_run.orcabus_id]
        )
        self.assertEqual(response.data["failed_count"], 1)
        self.assertEqual(response.data["failures"][0]["reason"], "NOT_FOUND")
        mock_emit_srsc_event.assert_called_once()

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_publish_failure_is_logged_after_commit(
        self, mock_emit_srsc_event
    ):
        actor = self.authenticate_state_actor()
        mock_emit_srsc_event.side_effect = RuntimeError("event bus unavailable")
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])
        State.objects.create(
            sequence=sequence_run,
            status="FAILED",
            timestamp=now(),
            comment="failed",
        )
        with self.assertLogs(
            "sequence_run_manager.viewsets.state", level="ERROR"
        ) as logs:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"{self.state_transition_endpoint}/resolve/",
                    {
                        "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                        "comment": "Handled",
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        state = State.objects.get(sequence=sequence_run, status="RESOLVED")
        sequence_run.refresh_from_db()
        self.assertEqual(sequence_run.status, "RESOLVED")
        mock_emit_srsc_event.assert_called_once()
        logged = " ".join(logs.output)
        self.assertIn("failed after database commit", logged)
        self.assertIn(str(sequence_run.orcabus_id), logged)
        self.assertIn(str(state.orcabus_id), logged)
        self.assertIn("recoverable=true", logged)

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_defers_srsc_publication_until_commit(
        self, mock_emit_srsc_event
    ):
        actor = self.authenticate_state_actor()
        sequence_run = Sequence.objects.get(sequence_run_id="r.AAAAAA")
        sequence_run.status = SequenceStatus.FAILED
        sequence_run.save(update_fields=["status"])

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.client.post(
                f"{self.state_transition_endpoint}/resolve/",
                {
                    "sequenceRunOrcabusIds": [sequence_run.orcabus_id],
                    "comment": "Handled",
                },
                format="json",
            )
            mock_emit_srsc_event.assert_not_called()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        mock_emit_srsc_event.assert_called_once()

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_state_transition_only_deprecate_when_no_current_sequence_status(
        self, mock_emit_srsc_event
    ):
        actor = self.authenticate_state_actor()
        orphan = Sequence.objects.create(
            instrument_run_id="orphan_run_001",
            run_volume_name="vol",
            run_folder_path="/p",
            run_data_uri="gds://vol/p",
            status=None,
            start_time=now(),
            sample_sheet_name="SampleSheet.csv",
            sequence_run_id="r.ORPHAN01",
            sequence_run_name="orphan_run_001",
            api_url="https://bssh.dev/api/v1/runs/r.ORPHAN01",
            v1pre3_id="1",
            ica_project_id="12345678-53ba-47a5-854d-e6b53101adb7",
            experiment_name="Exp",
        )
        bad = self.client.post(
            f"{self.state_transition_endpoint}/resolve/",
            {"sequenceRunOrcabusIds": [orphan.orcabus_id], "comment": "x"},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.data["failures"][0]["reason"], "INVALID_TRANSITION")
        self.assertIn("No current state found", bad.data["failures"][0]["detail"])
        mock_emit_srsc_event.assert_not_called()
        with self.captureOnCommitCallbacks(execute=True):
            good = self.client.post(
                f"{self.state_transition_endpoint}/deprecate/",
                {"sequenceRunOrcabusIds": [orphan.orcabus_id], "comment": "initial"},
                format="json",
            )
        self.assertEqual(good.status_code, 201)
        self.assertEqual(good.data["created_count"], 1)
        self.assertTrue(
            State.objects.filter(sequence=orphan, status="DEPRECATED").exists()
        )
        mock_emit_srsc_event.assert_called_once()
        srsc_event = mock_emit_srsc_event.call_args.args[0]
        self.assertEqual(srsc_event["orcabusId"], orphan.orcabus_id)
        self.assertEqual(srsc_event["status"], "DEPRECATED")
        self.assertEqual(srsc_event["stateCreatedBy"], actor)

    @patch("sequence_run_manager.viewsets.sequence_run_action.emit_srllc_api_event")
    @patch("sequence_run_manager.viewsets.sequence_run_action.emit_srssc_api_event")
    def test_add_samplesheet_action(self, mock_emit_srssc_event, mock_emit_srllc_event):
        """
        python manage.py test sequence_run_manager.tests.test_viewsets.SequenceViewSetTestCase.test_add_samplesheet_action
        """
        logger.info("Add samplesheet action")
        # Mock the event emission to avoid actual EventBridge calls
        mock_emit_srssc_event.return_value = None
        mock_emit_srllc_event.return_value = None

        # Read the file content from ./examples/standard-sheet-with-settings.csv
        samplesheet_path = (
            Path(__file__).parent / "examples/standard-sheet-with-settings.csv"
        )
        with open(samplesheet_path, "rb") as f:
            samplesheet_content = f.read()

        # Create a SimpleUploadedFile object to mock the file upload
        uploaded_file = SimpleUploadedFile(
            name="standard-sheet-with-settings.csv",
            content=samplesheet_content,
            content_type="text/csv",
        )

        # POST request with file upload using DRF's APIClient
        # format='multipart' is required for file uploads with APIClient
        add_samplesheet_response = self.client.post(
            f"{self.sequence_run_endpoint}/action/add_samplesheet/",
            data={
                "instrument_run_id": "190101_A01052_0001_BH5LY7ACGT",
                "created_by": "TestUser001",
                "comment": "TestComment",
                "file": uploaded_file,  # Include file in data dict for multipart
            },
            format="multipart",
        )

        self.assertEqual(
            add_samplesheet_response.status_code,
            200,
            f"Ok status response is expected, got {add_samplesheet_response.status_code}: {add_samplesheet_response.data}",
        )
        self.assertEqual(
            add_samplesheet_response.data["detail"],
            "Samplesheet added successfully",
            "Detail is expected",
        )
        mock_emit_srssc_event.assert_called_once()
        mock_emit_srllc_event.assert_called_once()

        # Get the created sequence_run (it's created by the add_samplesheet action)
        sequence_run = (
            Sequence.objects.filter(instrument_run_id="190101_A01052_0001_BH5LY7ACGT")
            .exclude(sequence_run_id="r.AAAAAA")
            .first()
        )
        self.assertIsNotNone(
            sequence_run, "Sequence run should be created by add_samplesheet action"
        )

        # test get samplesheet
        get_samplesheet_response = self.client.get(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/sample_sheet/"
        )
        self.assertEqual(
            get_samplesheet_response.status_code,
            200,
            f"Ok status response is expected, got {get_samplesheet_response.status_code}: {get_samplesheet_response.data}",
        )
        self.assertEqual(
            get_samplesheet_response.data["sample_sheet_name"],
            "standard-sheet-with-settings.csv",
            "Sample sheet name is expected",
        )
        self.assertEqual(
            get_samplesheet_response.data["sample_sheet_content_original"],
            samplesheet_content.decode("utf-8"),
            "Sample sheet content is expected",
        )

        # test get samplesheet by ss orcabus_id
        ss_orcabus_id = get_samplesheet_response.data["orcabus_id"]
        get_samplesheet_response = self.client.get(
            f"{self.sequence_run_endpoint}/{sequence_run.orcabus_id}/sample_sheet/{ss_orcabus_id}/"
        )
        self.assertEqual(
            get_samplesheet_response.status_code,
            200,
            f"Ok status response is expected, got {get_samplesheet_response.status_code}: {get_samplesheet_response.data}",
        )
        self.assertEqual(
            get_samplesheet_response.data["sample_sheet_name"],
            "standard-sheet-with-settings.csv",
            "Sample sheet name is expected",
        ),

        # test samplesheet api and cheksum query
        ss_orcabus_id = get_samplesheet_response.data["orcabus_id"]
        get_samplesheet_response = self.client.get(
            f"{self.sample_sheet_endpoint}/{ss_orcabus_id}/"
        )
        self.assertEqual(
            get_samplesheet_response.status_code,
            200,
            f"Ok status response is expected, got {get_samplesheet_response.status_code}: {get_samplesheet_response.data}",
        )
        self.assertEqual(
            get_samplesheet_response.data["sample_sheet_name"],
            "standard-sheet-with-settings.csv",
            "Sample sheet name is expected",
        )
        self.assertEqual(
            get_samplesheet_response.data["sample_sheet_content_original"],
            samplesheet_content.decode("utf-8"),
            "Sample sheet content is expected",
        )

        # test samplesheet api and cheksum query checksum
        sample_sheet_content_original = get_samplesheet_response.data[
            "sample_sheet_content_original"
        ]
        ss_checksum = hashlib.sha256(
            sample_sheet_content_original.encode("utf-8")
        ).hexdigest()
        get_samplesheet_checksum_response = self.client.get(
            f"{self.sample_sheet_endpoint}/?checksum={ss_checksum}&checksumType=sha256"
        )
        self.assertEqual(
            get_samplesheet_checksum_response.status_code,
            200,
            f"Ok status response is expected, got {get_samplesheet_checksum_response.status_code}: {get_samplesheet_checksum_response.data}",
        )
        self.assertEqual(
            len(get_samplesheet_checksum_response.data), 2, "One result is expected"
        )

        # test samplesheet api and cheksum query checksum by sequence run id
        get_samplesheet_checksum_response = self.client.get(
            f"{self.sample_sheet_endpoint}/?sequenceRunId=r.AAAAAA"
        )
        self.assertEqual(
            get_samplesheet_checksum_response.status_code,
            200,
            f"Ok status response is expected, got {get_samplesheet_checksum_response.status_code}: {get_samplesheet_checksum_response.data}",
        )
        self.assertEqual(
            len(get_samplesheet_checksum_response.data), 1, "One result is expected"
        )


@skipUnlessDBFeature("has_select_for_update")
class StateTransitionConcurrencyTestCase(TransactionTestCase):
    """Exercise real row-lock behavior using separate database connections."""

    reset_sequences = True
    state_transition_endpoint = f"/{api_base}sequence_run/state"

    def setUp(self):
        self.sequence = Sequence.objects.create(
            instrument_run_id="concurrent_run_001",
            run_volume_name="vol",
            run_folder_path="/runs/concurrent_run_001",
            run_data_uri="gds://vol/runs/concurrent_run_001",
            status=SequenceStatus.FAILED,
            start_time=now(),
            sample_sheet_name="SampleSheet.csv",
            sequence_run_id="r.CONCURRENT01",
            sequence_run_name="concurrent_run_001",
            api_url="https://bssh.dev/api/v1/runs/r.CONCURRENT01",
        )

    @patch("sequence_run_manager.viewsets.state.emit_srsc_api_event")
    def test_competing_resolved_transitions_create_one_state(
        self, mock_emit_srsc_event
    ):
        initial_read_barrier = Barrier(2)
        original_filter = Sequence.objects.filter
        responses = []
        errors = []

        def synchronized_initial_filter(*args, **kwargs):
            sequences = list(original_filter(*args, **kwargs))
            initial_read_barrier.wait(timeout=5)
            return sequences

        def post_transition():
            close_old_connections()
            try:
                client = APIClient()
                client.credentials(
                    HTTP_AUTHORIZATION=f"Bearer {_make_bearer_token('state.actor@example.org')}"
                )
                response = client.post(
                    f"{self.state_transition_endpoint}/resolve/",
                    {
                        "sequenceRunOrcabusIds": [self.sequence.orcabus_id],
                        "comment": "Handled",
                    },
                    format="json",
                )
                responses.append(response.status_code)
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        with patch.object(
            Sequence.objects,
            "filter",
            side_effect=synchronized_initial_filter,
        ):
            threads = [Thread(target=post_transition) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(responses), [201, 400])
        self.assertEqual(
            State.objects.filter(sequence=self.sequence, status="RESOLVED").count(),
            1,
        )
        mock_emit_srsc_event.assert_called_once()
