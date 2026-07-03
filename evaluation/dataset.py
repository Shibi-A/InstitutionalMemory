"""Load and validate semantic-search evaluation cases."""

import json
from pathlib import Path
from typing import Iterable


VALID_SPLITS = {"development", "test", "regression"}
VALID_OPERATIONS = {"query", "update", "feedback", "ingestion", "abstain"}
VALID_ENTITY_LABELS = {"Person", "Project", "Repository", "Role", "Skill"}
VALID_QUERY_INTENTS = {
    "direct_reports",
    "people_connection",
    "person_projects",
    "person_role",
    "person_summary",
    "person_supervisor",
    "project_contributors",
    "project_owner",
    "relationship_evidence",
    "skill_experts",
}
VALID_UPDATE_INTENTS = {
    "add_person",
    "add_person_to_project",
    "assign_project",
    "assign_role",
    "remove_person",
    "set_supervisor",
    "unassign_project",
}


def load_cases(path: Path) -> list[dict]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error
        case["_line_number"] = line_number
        cases.append(case)
    validate_cases(cases, path)
    for case in cases:
        case.pop("_line_number", None)
    return cases


def validate_cases(cases: Iterable[dict], path: Path = Path("<dataset>")) -> None:
    seen_ids = set()
    seen_queries = set()
    for case in cases:
        line_number = case.get("_line_number", "?")
        prefix = f"{path}:{line_number}"
        required = {"id", "split", "query", "expected", "tags"}
        missing = required - case.keys()
        if missing:
            raise ValueError(f"{prefix}: missing fields: {', '.join(sorted(missing))}")

        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{prefix}: id must be a non-empty string")
        if case_id in seen_ids:
            raise ValueError(f"{prefix}: duplicate id: {case_id}")
        seen_ids.add(case_id)

        query = case["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{prefix}: query must be a non-empty string")
        normalized_query = query.casefold().strip()
        if normalized_query in seen_queries:
            raise ValueError(f"{prefix}: duplicate query: {query}")
        seen_queries.add(normalized_query)

        if case["split"] not in VALID_SPLITS:
            raise ValueError(f"{prefix}: invalid split: {case['split']}")
        if not isinstance(case["tags"], list) or not case["tags"]:
            raise ValueError(f"{prefix}: tags must be a non-empty list")

        expected = case["expected"]
        if not isinstance(expected, dict) or "operation" not in expected:
            raise ValueError(f"{prefix}: expected.operation is required")
        operation = expected["operation"]
        if operation not in VALID_OPERATIONS:
            raise ValueError(f"{prefix}: invalid operation: {operation}")

        intent = expected.get("intent")
        valid_intents = (
            VALID_QUERY_INTENTS
            if operation == "query"
            else VALID_UPDATE_INTENTS
            if operation == "update"
            else set()
        )
        if operation in {"query", "update"} and intent is None:
            raise ValueError(f"{prefix}: {operation} cases require an expected intent")
        if intent is not None and intent not in valid_intents:
            raise ValueError(f"{prefix}: invalid intent {intent!r} for {operation}")

        entities = expected.get("entities", [])
        if not isinstance(entities, list):
            raise ValueError(f"{prefix}: expected.entities must be a list")
        for entity in entities:
            if set(entity) != {"label", "name"}:
                raise ValueError(f"{prefix}: entities require exactly label and name")
            if entity["label"] not in VALID_ENTITY_LABELS:
                raise ValueError(f"{prefix}: invalid entity label: {entity['label']}")
            if not isinstance(entity["name"], str) or not entity["name"]:
                raise ValueError(f"{prefix}: entity name must be a non-empty string")

        if operation == "abstain" and (intent is not None or entities):
            raise ValueError(f"{prefix}: abstention cases cannot specify intent or entities")
