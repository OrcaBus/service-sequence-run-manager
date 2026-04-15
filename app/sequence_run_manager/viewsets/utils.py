"""
Shared helpers for viewsets: JWT/Bearer parsing and sequence-run list query building.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import jwt
from django.db.models import Count, Max, Min, OuterRef, Q, QuerySet, Subquery
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.settings import api_settings

from sequence_run_manager.pagination import PaginationConstant
from sequence_run_manager.models import Sequence, SequenceStatus, LibraryAssociation

logger = logging.getLogger(__name__)

SEQUENCE_STATUS_QUERY_VALUES = frozenset(member.value for member in SequenceStatus)


# --- Bearer / JWT (used by comment and similar viewsets) ---


def parse_bearer_raw_token_from_request(request, keyword: str = "Bearer") -> Optional[str]:
    """
    Extract the JWT string from ``Authorization: Bearer <token>``.

    Returns ``None`` if the header is missing or not a single Bearer token.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return None

    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != keyword.lower():
        return None

    raw_token = parts[1].strip()
    return raw_token or None


def decode_rs256_jwt_payload_without_verification(raw_token: str) -> dict[str, Any]:
    """
    Decode a JWT's payload with alg RS256. Signature is **not** verified.

    Use when an upstream layer (e.g. API Gateway) has already authenticated the caller;
    this only reads claims such as ``email``.
    """
    try:
        return jwt.decode(
            raw_token,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
    except jwt.PyJWTError as exc:
        logger.info("JWT decode failed: %s", exc)
        raise AuthenticationFailed("Invalid token.") from exc


def get_email_from_bearer_authorization(request, keyword: str = "Bearer") -> str:
    """
    Normalized ``email`` claim from ``Authorization: Bearer <jwt>``.

    Raises:
        AuthenticationFailed: Missing/malformed Bearer header, invalid token, or no email claim.
    """
    raw_token = parse_bearer_raw_token_from_request(request, keyword=keyword)
    if not raw_token:
        raise AuthenticationFailed("Authentication credentials were not provided.")
    payload = decode_rs256_jwt_payload_without_verification(raw_token)
    email = payload.get("email")
    if email and isinstance(email, str) and email.strip():
        return email.strip().lower()
    raise AuthenticationFailed("Token payload did not contain a valid email claim.")


# --- Sequence run list-style query (list / list_by_instrument_run_id / stats) ---

# Query params handled by views / DRF — never pass through to ``get_by_keyword`` / ORM iexact stack.
SEQUENCE_RUN_NON_KEYWORD_QUERY_PARAMS = frozenset(
    {
        "start_time",
        "end_time",
        "library_id",
        "status",
        api_settings.ORDERING_PARAM,
        api_settings.SEARCH_PARAM,
        PaginationConstant.PAGE,
        PaginationConstant.ROWS_PER_PAGE,
        "sortCol",
        "sortAsc",
    }
)


def parse_datetime_safe(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    return parse_datetime(value.strip())


def build_keyword_params(query_params) -> dict[str, list[str]]:
    """
    Build keyword args for ``get_by_keyword`` / ``get_model_fields_query``.

    Uses ``getlist`` so repeated keys stay as multiple values (e.g. several workflow ids).
    Each value is stripped; blanks are dropped. A key is omitted entirely if every value
    is blank, so we never apply ``field__iexact=''`` from params like ``?workflow_id=``.
    """
    out: dict[str, list[str]] = {}
    for k in query_params:
        if k in SEQUENCE_RUN_NON_KEYWORD_QUERY_PARAMS:
            continue
        raw = query_params.getlist(k)
        if not raw:
            continue
        values: list[str] = []
        for v in raw:
            s = v.strip() if isinstance(v, str) else str(v).strip()
            if s:
                values.append(s)
        if values:
            out[k] = values
    return out


def _sequence_run_search_q(term: str) -> Q:
    """
    Search query for sequence runs using a case-insensitive substring match on orcabus_id, instrument_run_id, sequence_run_id, sequence_run_name, experiment_name, and sample_sheet_name
    """
    return (
        Q(orcabus_id__icontains=term)
        | Q(instrument_run_id__icontains=term)
        | Q(sequence_run_id__icontains=term)
        | Q(sequence_run_name__icontains=term)
        | Q(experiment_name__icontains=term)
        | Q(sample_sheet_name__icontains=term)
    )


def filtered_sequence_runs_queryset(
    query_params,
    *,
    apply_sequence_status_param: bool = True,
) -> QuerySet:
    """
    Keyword filters, exclude fake runs (``status`` null), optional ``start_time`` / ``end_time``
    (parsed datetimes, applied to ``Sequence.start_time`` as gte/lte), ``library_id``,
    optional ``status`` on ``Sequence.status`` (only when ``apply_sequence_status_param`` is True),
    and free-text search using ``api_settings.SEARCH_PARAM`` (default ``search``).

    For ``list_by_instrument_run_id`` / instrument-run stats, pass
    ``apply_sequence_status_param=False`` so ``status`` filters the **group** status instead.

    Raises:
        ValidationError: If ``status`` is present and non-blank but not a ``SequenceStatus`` value.
    """
    status_filter = (query_params.get("status") or "").strip()
    if status_filter and status_filter not in SEQUENCE_STATUS_QUERY_VALUES:
        raise ValidationError(f"Invalid status value: {status_filter}")

    keyword_params = build_keyword_params(query_params)
    qs = (
        Sequence.objects.get_by_keyword(**keyword_params)
        .distinct()
        .filter(status__isnull=False)
    )

    start_time = query_params.get("start_time")
    end_time = query_params.get("end_time")
    start_dt = parse_datetime_safe(start_time) if start_time else None
    end_dt = parse_datetime_safe(end_time) if end_time else None
    if start_dt:
        qs = qs.filter(start_time__gte=start_dt)
    if end_dt:
        qs = qs.filter(start_time__lte=end_dt)

    library_id = query_params.get("library_id")
    if library_id:
        sequence_ids = LibraryAssociation.objects.filter(library_id=library_id).values_list(
            "sequence_id", flat=True
        )
        qs = qs.filter(orcabus_id__in=sequence_ids)

    if apply_sequence_status_param:
        if status_filter:
            qs = qs.filter(status=status_filter)

    search_term = query_params.get(api_settings.SEARCH_PARAM, "") or ""
    if search_term:
        qs = qs.filter(_sequence_run_search_q(search_term))

    return qs


def instrument_run_groups_queryset(sequence_set: QuerySet) -> QuerySet:
    """
    One row per non-empty ``instrument_run_id`` in ``sequence_set``, with the same aggregates as
    ``list_by_instrument_run_id`` plus ``group_status``: ``status`` of the row with latest
    ``start_time`` (ties broken by ``orcabus_id`` desc), among rows with non-null ``status``.
    """
    latest_status_sq = Subquery(
        sequence_set.filter(
            instrument_run_id=OuterRef("instrument_run_id"),
            status__isnull=False,
        )
        .order_by("-start_time", "-orcabus_id")
        .values("status")[:1]
    )
    return (
        sequence_set.filter(instrument_run_id__isnull=False)
        .exclude(instrument_run_id="")
        .values("instrument_run_id")
        .annotate(
            # Distinct sequence rows (avoids duplicate joins); matches rows in ``items``.
            count=Count("orcabus_id", distinct=True),
            start_time=Min("start_time"),
            end_time=Max("end_time"),
            group_status=latest_status_sq,
        )
        .order_by("-start_time")
    )
