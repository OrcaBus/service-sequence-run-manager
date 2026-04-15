"""Tests for ``sequence_run_manager.viewsets.utils`` helpers."""

from django.http import QueryDict
from django.test import SimpleTestCase

from sequence_run_manager.viewsets.utils import build_keyword_params


class BuildKeywordParamsTests(SimpleTestCase):
    def test_blank_only_param_omitted(self):
        q = QueryDict("workflow_id=")
        self.assertEqual(build_keyword_params(q), {})

    def test_whitespace_only_param_omitted(self):
        q = QueryDict(mutable=True)
        q.setlist("workflow_id", ["  ", "\t"])
        self.assertEqual(build_keyword_params(q), {})

    def test_strips_and_keeps_non_blank(self):
        q = QueryDict(mutable=True)
        q.setlist("workflow_id", ["  a ", "b"])
        self.assertEqual(build_keyword_params(q), {"workflow_id": ["a", "b"]})

    def test_mixed_blank_and_real_values(self):
        q = QueryDict(mutable=True)
        q.setlist("workflow_id", ["", "x", "  "])
        self.assertEqual(build_keyword_params(q), {"workflow_id": ["x"]})
