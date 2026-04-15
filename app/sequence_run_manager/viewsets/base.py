from __future__ import annotations

from abc import ABC

from sequence_run_manager.pagination import StandardResultsSetPagination
from rest_framework import filters
from rest_framework.viewsets import ReadOnlyModelViewSet


class BaseViewSet(ReadOnlyModelViewSet, ABC):
    lookup_value_regex = "[^/]+"  # This is to allow for special characters in the URL
    ordering_fields = "__all__"
    ordering = ["-orcabus_id"]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
