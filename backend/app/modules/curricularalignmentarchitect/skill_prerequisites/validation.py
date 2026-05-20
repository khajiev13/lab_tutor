from __future__ import annotations

from .schemas import PrerequisiteDraftEdge, PrerequisiteValidationRead


def compute_isolated_skills(
    skill_names: list[str],
    edges: list[PrerequisiteDraftEdge],
) -> list[str]:
    connected: set[str] = set()
    for edge in edges:
        connected.add(edge.prerequisite_name)
        connected.add(edge.dependent_name)
    return sorted({name for name in skill_names if name not in connected})


def validate_prerequisite_edges(
    *,
    skill_names: list[str],
    edges: list[PrerequisiteDraftEdge],
) -> PrerequisiteValidationRead:
    errors: list[str] = []
    skill_set = set(skill_names)
    seen: set[tuple[str, str]] = set()

    for edge in edges:
        pair = (edge.prerequisite_name, edge.dependent_name)
        if (
            edge.prerequisite_name not in skill_set
            or edge.dependent_name not in skill_set
        ):
            errors.append(
                f"Unknown skill in edge: {edge.prerequisite_name} -> {edge.dependent_name}"
            )
            continue
        if edge.prerequisite_name == edge.dependent_name:
            errors.append(f"Self prerequisite is not allowed: {edge.prerequisite_name}")
            continue
        if pair in seen:
            errors.append(
                f"Duplicate prerequisite edge: {edge.prerequisite_name} -> {edge.dependent_name}"
            )
            continue
        seen.add(pair)

    cycle_path = _find_cycle_path(
        [
            edge
            for edge in edges
            if edge.prerequisite_name in skill_set
            and edge.dependent_name in skill_set
            and edge.prerequisite_name != edge.dependent_name
        ]
    )
    if cycle_path:
        errors.append(f"Cycle detected: {' -> '.join(cycle_path)}")

    return PrerequisiteValidationRead(
        is_valid=not errors,
        errors=errors,
        cycle_path=cycle_path,
    )


def _find_cycle_path(edges: list[PrerequisiteDraftEdge]) -> list[str]:
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.prerequisite_name, []).append(edge.dependent_name)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return []

        visiting.add(node)
        stack.append(node)
        for neighbor in adjacency.get(node, []):
            cycle = visit(neighbor)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in adjacency:
        cycle = visit(node)
        if cycle:
            return cycle
    return []
