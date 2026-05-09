from __future__ import annotations

import json
from collections.abc import Iterable

from fastapi import Request

DEFAULT_KNOWN_PARAMS = {"limit", "offset", "category_id", "sort", "search", "filters"}


def parse_filters(
    request: Request,
    *,
    allow_unscoped: bool = False,
    known_params: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    params = list(request.query_params.multi_items())

    for key, value in params:
        if key.startswith("filters[") and key.endswith("]"):
            name = key[len("filters[") : -1]
            if name:
                filters.setdefault(name, []).append(value)

    raw_filters = request.query_params.get("filters")
    if raw_filters:
        try:
            parsed = json.loads(raw_filters)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid filters format") from exc
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                if isinstance(value, list):
                    for item in value:
                        filters.setdefault(str(key), []).append(str(item))
                else:
                    filters.setdefault(str(key), []).append(str(value))

    if allow_unscoped and not filters:
        allowed = set(known_params or DEFAULT_KNOWN_PARAMS)
        for key, value in params:
            if key in allowed:
                continue
            filters.setdefault(key, []).append(value)

    return filters
