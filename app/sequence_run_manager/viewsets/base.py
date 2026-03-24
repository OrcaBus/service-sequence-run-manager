from __future__ import annotations

import logging
from abc import ABC
from typing import Any, Optional

import jwt

from sequence_run_manager.pagination import StandardResultsSetPagination
from rest_framework import filters
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.viewsets import ReadOnlyModelViewSet

logger = logging.getLogger(__name__)

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
class BaseViewSet(ReadOnlyModelViewSet, ABC):
    lookup_value_regex = "[^/]+"  # This is to allow for special characters in the URL
    ordering_fields = "__all__"
    ordering = ["-orcabus_id"]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
