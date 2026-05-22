from __future__ import annotations

from collections.abc import Iterable

from fastapi import Request

DEFAULT_KNOWN_PARAMS = {
    "limit",
    "offset",
    "category_id",
    "sort",
    "q",
    "search",
    "filter",
    "filters",
}


def parse_filters(
    request: Request,
    *,
    allow_unscoped: bool = False,
    known_params: Iterable[str] | None = None,
    prefixes: Iterable[str] = ("filter", "filters"),
) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    params = list(request.query_params.multi_items())

    for key, value in params:
        for prefix in prefixes:
            bracket_prefix = f"{prefix}["
            if key.startswith(bracket_prefix) and key.endswith("]"):
                name = key[len(bracket_prefix) : -1]
                if name:
                    filters.setdefault(name, []).append(value)
                break

    if allow_unscoped and not filters:
        allowed = set(known_params or DEFAULT_KNOWN_PARAMS)
        for key, value in params:
            if key in allowed:
                continue
            filters.setdefault(key, []).append(value)

    return filters
