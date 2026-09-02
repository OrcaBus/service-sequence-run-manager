"""Tests for ``sequence_run_manager.serializers`` helpers."""

from django.test import SimpleTestCase
from rest_framework import serializers

from sequence_run_manager.serializers.base import (
    OrcabusIdListField,
    OrcabusIdListUtils,
)
from sequence_run_manager.serializers.state import StateTransitionRequestSerializer


class OrcabusIdListUtilsTests(SimpleTestCase):
    def test_none_returns_empty_list(self):
        self.assertEqual(OrcabusIdListUtils.normalize(None), [])

    def test_comma_separated_string_is_split_and_stripped(self):
        self.assertEqual(
            OrcabusIdListUtils.normalize(" seq.AAA , seq.BBB ,, "),
            ["seq.AAA", "seq.BBB"],
        )

    def test_blank_string_returns_empty_list(self):
        self.assertEqual(OrcabusIdListUtils.normalize("  "), [])

    def test_list_drops_none_and_blank_items(self):
        self.assertEqual(
            OrcabusIdListUtils.normalize(["seq.AAA", None, "  ", "seq.BBB"]),
            ["seq.AAA", "seq.BBB"],
        )

    def test_list_expands_comma_separated_items(self):
        self.assertEqual(
            OrcabusIdListUtils.normalize(["seq.AAA, seq.BBB", "seq.CCC"]),
            ["seq.AAA", "seq.BBB", "seq.CCC"],
        )

    def test_tuple_is_accepted(self):
        self.assertEqual(
            OrcabusIdListUtils.normalize(("seq.AAA", "seq.BBB")),
            ["seq.AAA", "seq.BBB"],
        )

    def test_non_string_scalar_is_coerced_to_single_item_list(self):
        self.assertEqual(OrcabusIdListUtils.normalize(123), ["123"])

    def test_falsy_non_string_scalar_returns_empty_list(self):
        self.assertEqual(OrcabusIdListUtils.normalize(0), [])


class OrcabusIdListFieldTests(SimpleTestCase):
    class _DummySerializer(serializers.Serializer):
        ids = OrcabusIdListField(child=serializers.CharField(allow_blank=False))

    def test_field_normalizes_csv_string(self):
        serializer = self._DummySerializer(data={"ids": "seq.AAA,seq.BBB"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["ids"],
            ["seq.AAA", "seq.BBB"],
        )

    def test_transition_request_accepts_csv_string(self):
        serializer = StateTransitionRequestSerializer(
            data={
                "sequence_run_orcabus_ids": "seq.AAA, seq.BBB",
                "comment": "Handled",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["sequence_run_orcabus_ids"],
            ["seq.AAA", "seq.BBB"],
        )

    def test_transition_request_rejects_empty_id_list(self):
        serializer = StateTransitionRequestSerializer(
            data={"sequence_run_orcabus_ids": "  ", "comment": "Handled"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("sequence_run_orcabus_ids", serializer.errors)
