from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _Category:
    id: str
    name: str
    parent_id: str | None
    level: int
    path: list[str]


_CATEGORIES: list[_Category] = [
    _Category(
        id="550e8400-e29b-41d4-a716-446655440010",
        name="Phones",
        parent_id=None,
        level=0,
        path=["Phones"],
    ),
    _Category(
        id="550e8400-e29b-41d4-a716-446655440011",
        name="Smartphones",
        parent_id="550e8400-e29b-41d4-a716-446655440010",
        level=1,
        path=["Phones", "Smartphones"],
    ),
    _Category(
        id="550e8400-e29b-41d4-a716-446655440012",
        name="Accessories",
        parent_id="550e8400-e29b-41d4-a716-446655440010",
        level=1,
        path=["Phones", "Accessories"],
    ),
]


def build_tree() -> list[dict[str, object]]:
    children_map: dict[str, list[_Category]] = {category.id: [] for category in _CATEGORIES}
    for category in _CATEGORIES:
        if category.parent_id is not None and category.parent_id in children_map:
            children_map[category.parent_id].append(category)

    def _node(category: _Category) -> dict[str, object]:
        return {
            "id": category.id,
            "name": category.name,
            "parent_id": category.parent_id,
            "level": category.level,
            "path": list(category.path),
            "children": [_node(child) for child in children_map.get(category.id, [])],
        }

    roots = [category for category in _CATEGORIES if category.parent_id is None]
    return [_node(root) for root in roots]


def breadcrumbs(category_id: str | None) -> list[dict[str, str]]:
    if category_id is None:
        return []
    by_id = {category.id: category for category in _CATEGORIES}
    current = by_id.get(category_id)
    if current is None:
        return []

    trail: list[_Category] = []
    while current is not None:
        trail.append(current)
        if current.parent_id is None:
            break
        current = by_id.get(current.parent_id)

    return [{"id": category.id, "name": category.name} for category in reversed(trail)]
