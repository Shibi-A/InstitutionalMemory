"""Apply controlled natural-language updates to the Neo4j graph."""

import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring.semantic_search import score_semantic_matches
from evidence.service import add_contribution_evidence, remove_contribution_evidence


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

CONTRIBUTION_TYPES = ("DESIGNS", "IMPLEMENTED", "OWNED")


@dataclass(frozen=True)
class MutationIntent:
    name: str
    examples: tuple[str, ...]


INTENTS = (
    MutationIntent(
        "add_person_to_project",
        (
            "Chris joined the company and works on Frontend",
            "Add a new person to a project",
            "Hire someone to work on a project",
        ),
    ),
    MutationIntent(
        "add_person",
        (
            "Add Chris",
            "Chris joined the company",
            "Hire a new person",
        ),
    ),
    MutationIntent(
        "remove_person",
        (
            "Remove Shibi",
            "Delete this person",
            "This person left the company",
        ),
    ),
    MutationIntent(
        "assign_project",
        (
            "Chris works on Frontend",
            "Assign this person to a project",
            "This person now designs the UI project",
        ),
    ),
    MutationIntent(
        "unassign_project",
        (
            "Shibi no longer works on Frontend",
            "Remove this person from the project",
            "This person stopped implementing Backend",
        ),
    ),
    MutationIntent(
        "assign_role",
        (
            "Chris is a Frontend Engineer",
            "Assign this person a role",
            "This person became a manager",
        ),
    ),
    MutationIntent(
        "set_supervisor",
        (
            "Chris works under Alice",
            "Set this person's supervisor",
            "This person reports to Bob",
        ),
    ),
)


def classify_intent(command: str) -> tuple[MutationIntent, float]:
    lowered = command.lower()
    if (
        any(phrase in lowered for phrase in ("joined", "add ", "hire "))
        and "works on" in lowered
    ):
        intent = next(
            intent for intent in INTENTS if intent.name == "add_person_to_project"
        )
        return intent, 1.0

    phrase_rules = (
        ("unassign_project", ("no longer works on", "stopped implementing", "remove from")),
        ("set_supervisor", ("works under", "reports to", "set supervisor")),
        ("add_person", (" joined ", "joined ", "add ", "hire ")),
        ("remove_person", ("remove ", "delete ", " left ", "left ")),
        ("assign_role", (" role", "became a ", "became an ")),
        (
            "assign_project",
            (
                "works on",
                "assign ",
                "designs ",
                "implemented ",
                "owns ",
                " built ",
                "builds ",
                "developed ",
                "created ",
            ),
        ),
    )
    for intent_name, phrases in phrase_rules:
        if any(phrase in lowered for phrase in phrases):
            intent = next(intent for intent in INTENTS if intent.name == intent_name)
            return intent, 1.0

    example_to_intent = {
        example: intent
        for intent in INTENTS
        for example in intent.examples
    }
    match = score_semantic_matches(command, example_to_intent, limit=1)[0]
    return example_to_intent[match.text], match.confidence


def get_names(driver, label: str) -> list[str]:
    query = f"""
    MATCH (entity:{label})
    WHERE entity.name IS NOT NULL
    RETURN entity.name AS name
    ORDER BY name
    """
    records, _, _ = driver.execute_query(query, database_="neo4j")
    return [record["name"] for record in records]


def find_exact_mentions(text: str, candidates: list[str]) -> list[str]:
    lowered_text = text.lower()
    return sorted(
        (name for name in candidates if name.lower() in lowered_text),
        key=len,
        reverse=True,
    )


def resolve_existing_name(
    command: str,
    label: str,
    candidates: list[str],
    excluded: Optional[set[str]] = None,
) -> tuple[str, float]:
    available = [name for name in candidates if name not in (excluded or set())]
    exact = find_exact_mentions(command, available)
    if exact:
        return exact[0], 1.0
    if not available:
        raise ValueError(f"No {label} nodes are available.")

    match = score_semantic_matches(command, available, limit=1)[0]
    print(f'Closest {label}: "{match.text}" ({match.confidence:.1%})')
    value = input(f'Use "{match.text}"? [y/N], or enter another name: ').strip()
    if value.lower() == "y":
        return match.text, match.confidence
    if value:
        matching_name = next(
            (name for name in available if name.lower() == value.lower()),
            None,
        )
        if matching_name:
            return matching_name, 1.0
    raise ValueError(f"A valid existing {label} is required.")


def extract_new_person_name(command: str) -> Optional[str]:
    patterns = (
        r"^\s*(.+?)\s+joined\b",
        r"\b(?:add|hire)\s+(.+?)(?:\s+to\b|\s+as\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, command, re.IGNORECASE)
        if match:
            name = match.group(1).strip(" .")
            if name:
                return name.title()
    return None


def parse_project_assignment(command: str) -> Optional[tuple[str, str, str]]:
    match = re.match(
        r"^\s*(.+?)\s+"
        r"(builds?|built|created?|designs?|developed?|implemented?|implements?|owns?)"
        r"\s+(.+?)\s*$",
        command,
        re.IGNORECASE,
    )
    if not match:
        return None

    contribution = resolve_contribution(match.group(2))
    project = re.sub(r"^the\s+", "", match.group(3).strip(" ."), flags=re.IGNORECASE)
    return (
        match.group(1).strip(" ."),
        contribution,
        project,
    )


def canonical_name(name: str, candidates: list[str]) -> Optional[str]:
    return next(
        (candidate for candidate in candidates if candidate.lower() == name.lower()),
        None,
    )


def prompt_new_name(label: str, suggested: Optional[str] = None) -> str:
    prompt = f"New {label} name"
    if suggested:
        prompt += f" [{suggested}]"
    value = input(f"{prompt}: ").strip() or suggested
    if not value:
        raise ValueError(f"A {label} name is required.")
    return value


def resolve_contribution(command: str, allow_all: bool = False) -> Optional[str]:
    lowered = command.lower()
    keyword_types = {
        "build": "IMPLEMENTED",
        "built": "IMPLEMENTED",
        "create": "IMPLEMENTED",
        "design": "DESIGNS",
        "develop": "IMPLEMENTED",
        "implement": "IMPLEMENTED",
        "own": "OWNED",
    }
    for keyword, relationship_type in keyword_types.items():
        if keyword in lowered:
            return relationship_type

    choices = "/".join(CONTRIBUTION_TYPES)
    if allow_all:
        choices += "/ALL"
    value = input(f"Contribution type ({choices}): ").strip().upper()
    allowed = set(CONTRIBUTION_TYPES)
    if allow_all:
        allowed.add("ALL")
    if value not in allowed:
        raise ValueError("A valid contribution type is required.")
    return None if value == "ALL" else value


def confirm(preview: str) -> bool:
    print(f"\nProposed change: {preview}")
    confirmed = input("Apply this change? [y/N]: ").strip().lower() == "y"
    if not confirmed:
        print("Update cancelled. No changes were made.")
    return confirmed


def run_write(driver, cypher: str, parameters: dict) -> None:
    records, summary, _ = driver.execute_query(
        cypher,
        parameters_=parameters,
        database_="neo4j",
    )
    for record in records:
        print(f"- {record.data()}")
    counters = summary.counters
    print(
        "Changes: "
        f"nodes created={counters.nodes_created}, "
        f"nodes deleted={counters.nodes_deleted}, "
        f"relationships created={counters.relationships_created}, "
        f"relationships deleted={counters.relationships_deleted}"
    )
    print("Update acknowledged and completed successfully.")


def add_person(driver, command: str) -> None:
    person = prompt_new_name("person", extract_new_person_name(command))
    if not confirm(f'add Person "{person}"'):
        return
    run_write(
        driver,
        "MERGE (person:Person {name: $person}) RETURN person.name AS person",
        {"person": person},
    )


def add_person_to_project(driver, command: str) -> None:
    person = prompt_new_name("person", extract_new_person_name(command))
    project, _ = resolve_existing_name(command, "Project", get_names(driver, "Project"))
    contribution = resolve_contribution(command)
    if not confirm(f'add Person "{person}" and create {contribution} -> {project}'):
        return
    evidence_id = add_contribution_evidence(
        driver,
        person=person,
        project=project,
        contribution_type=contribution,
        level="explicit",
        source="manual_update",
        statement=command,
    )
    print(f"Evidence recorded: {evidence_id}")
    print("Update acknowledged and completed successfully.")


def remove_person(driver, command: str) -> None:
    person, _ = resolve_existing_name(command, "Person", get_names(driver, "Person"))
    records, _, _ = driver.execute_query(
        """
        MATCH (person:Person)
        WHERE toLower(person.name) = toLower($person)
        OPTIONAL MATCH (person)-[outgoing]->()
        OPTIONAL MATCH ()-[incoming]->(person)
        RETURN count(DISTINCT outgoing) + count(DISTINCT incoming) AS relationships
        """,
        person=person,
        database_="neo4j",
    )
    relationship_count = records[0]["relationships"]
    if not confirm(
        f'delete Person "{person}" and {relationship_count} relationship(s)'
    ):
        return
    run_write(
        driver,
        """
        MATCH (person:Person)
        WHERE toLower(person.name) = toLower($person)
        WITH person, person.name AS removed
        DETACH DELETE person
        RETURN removed
        """,
        {"person": person},
    )


def assign_project(driver, command: str) -> None:
    people = get_names(driver, "Person")
    projects = get_names(driver, "Project")
    parsed_assignment = parse_project_assignment(command)
    if parsed_assignment:
        supplied_person, contribution, supplied_project = parsed_assignment
        person = canonical_name(supplied_person, people) or supplied_person
        project = canonical_name(supplied_project, projects) or supplied_project.title()
        additions = []
        if person not in people:
            additions.append(f'add Person "{person}"')
        if project not in projects:
            additions.append(f'add Project "{project}"')
        additions.append(f"{person} -[:{contribution}]-> {project}")
        if not confirm(" and ".join(additions)):
            return
        evidence_id = add_contribution_evidence(
            driver,
            person=person,
            project=project,
            contribution_type=contribution,
            level="explicit",
            source="manual_update",
            statement=command,
        )
        print(f"Evidence recorded: {evidence_id}")
        print("Update acknowledged and completed successfully.")
        return

    exact_people = find_exact_mentions(command, people)
    if exact_people:
        person = exact_people[0]
    else:
        suggested = extract_new_person_name(command)
        if suggested and input(
            f'Person "{suggested}" does not exist. Add them? [y/N]: '
        ).strip().lower() == "y":
            run_write(
                driver,
                "MERGE (person:Person {name: $person}) RETURN person.name AS person",
                {"person": suggested},
            )
            person = suggested
        else:
            person, _ = resolve_existing_name(command, "Person", people)
    project, _ = resolve_existing_name(command, "Project", projects)
    contribution = resolve_contribution(command)
    if not confirm(f'{person} -[:{contribution}]-> {project}'):
        return
    evidence_id = add_contribution_evidence(
        driver,
        person=person,
        project=project,
        contribution_type=contribution,
        level="explicit",
        source="manual_update",
        statement=command,
    )
    print(f"Evidence recorded: {evidence_id}")
    print("Update acknowledged and completed successfully.")


def unassign_project(driver, command: str) -> None:
    person, _ = resolve_existing_name(command, "Person", get_names(driver, "Person"))
    project, _ = resolve_existing_name(command, "Project", get_names(driver, "Project"))
    contribution = resolve_contribution(command, allow_all=True)
    description = contribution or "all contribution relationships"
    if not confirm(f"remove {description} between {person} and {project}"):
        return
    removed = remove_contribution_evidence(
        driver,
        person=person,
        project=project,
        contribution_type=contribution,
    )
    print(f"Removed {removed} evidence record(s).")
    print("Update acknowledged and completed successfully.")


def assign_role(driver, command: str) -> None:
    person, _ = resolve_existing_name(command, "Person", get_names(driver, "Person"))
    roles = get_names(driver, "Role")
    exact_roles = find_exact_mentions(command, roles)
    role = exact_roles[0] if exact_roles else prompt_new_name("role")
    if not confirm(f'{person} -[:IS]-> {role}'):
        return
    run_write(
        driver,
        """
        MATCH (person:Person)
        WHERE toLower(person.name) = toLower($person)
        MERGE (role:Role {name: $role})
        MERGE (person)-[:IS]->(role)
        RETURN person.name AS person, role.name AS role
        """,
        {"person": person, "role": role},
    )


def set_supervisor(driver, command: str) -> None:
    people = get_names(driver, "Person")
    mentions = find_exact_mentions(command, people)
    if len(mentions) >= 2:
        person, supervisor = mentions[-1], mentions[0]
        works_under_match = re.search(
            r"(.+?)\s+(?:works under|reports to)\s+(.+)",
            command,
            re.IGNORECASE,
        )
        if works_under_match:
            first = find_exact_mentions(works_under_match.group(1), people)
            second = find_exact_mentions(works_under_match.group(2), people)
            if first and second:
                person, supervisor = first[0], second[0]
    else:
        person, _ = resolve_existing_name(command, "Person", people)
        supervisor, _ = resolve_existing_name(
            command,
            "Person",
            people,
            excluded={person},
        )
    if person == supervisor:
        raise ValueError("A person cannot supervise themselves.")
    if not confirm(f"{person} works under {supervisor}"):
        return
    run_write(
        driver,
        """
        MATCH (person:Person), (supervisor:Person)
        WHERE toLower(person.name) = toLower($person)
          AND toLower(supervisor.name) = toLower($supervisor)
        OPTIONAL MATCH (person)-[oldUnder:WORKS_UNDER]->(oldSupervisor:Person)
        OPTIONAL MATCH (oldSupervisor)-[oldSupervises:SUPERVISES]->(person)
        DELETE oldUnder, oldSupervises
        MERGE (person)-[:WORKS_UNDER]->(supervisor)
        MERGE (supervisor)-[:SUPERVISES]->(person)
        RETURN person.name AS person, supervisor.name AS supervisor
        """,
        {"person": person, "supervisor": supervisor},
    )


HANDLERS: dict[str, Callable] = {
    "add_person_to_project": add_person_to_project,
    "add_person": add_person,
    "remove_person": remove_person,
    "assign_project": assign_project,
    "unassign_project": unassign_project,
    "assign_role": assign_role,
    "set_supervisor": set_supervisor,
}


def apply_update(command: str) -> int:
    if not command:
        print("An update command is required.")
        return 1

    try:
        intent, confidence = classify_intent(command)
        print(f"Matched update: {intent.name} ({confidence:.1%})")
        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            HANDLERS[intent.name](driver, command)
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not update Neo4j: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Could not apply graph update: {error}", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    command = input("Describe a graph update: ").strip()
    return apply_update(command)


if __name__ == "__main__":
    raise SystemExit(main())
