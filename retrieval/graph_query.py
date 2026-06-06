"""Handle read-only graph retrieval using local Chroma intent matching."""

import os
import sys
from dataclasses import dataclass
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring.semantic_search import score_semantic_matches


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


@dataclass(frozen=True)
class Intent:
    name: str
    examples: tuple[str, ...]
    entity_labels: tuple[str, ...]
    cypher: str


INTENTS = (
    Intent(
        name="person_summary",
        examples=(
            "What does this person do?",
            "Tell me about this person",
            "Summarize this person's work",
        ),
        entity_labels=("Person",),
        cypher="""
        MATCH (person:Person)
        WHERE toLower(person.name) = toLower($entity_0)
        OPTIONAL MATCH (person)-[:IS]->(role:Role)
        OPTIONAL MATCH (person)-[work:DESIGNS|IMPLEMENTED|OWNED]->(project:Project)
        OPTIONAL MATCH (person)-[:WORKS_UNDER]->(supervisor:Person)
        OPTIONAL MATCH (person)-[:SUPERVISES]->(directReport:Person)
        RETURN person.name AS person,
               collect(DISTINCT role.name) AS roles,
               collect(DISTINCT project.name) AS projects,
               collect(DISTINCT type(work)) AS contributions,
               collect(DISTINCT supervisor.name) AS supervisors,
               collect(DISTINCT directReport.name) AS direct_reports
        """,
    ),
    Intent(
        name="project_owner",
        examples=(
            "Who owns the project?",
            "Who is responsible for the project?",
            "Who owns the API work?",
        ),
        entity_labels=("Project",),
        cypher="""
        MATCH (person:Person)-[:OWNED]->(project:Project)
        WHERE toLower(project.name) = toLower($entity_0)
        RETURN person.name AS owner, project.name AS project
        ORDER BY owner
        """,
    ),
    Intent(
        name="person_projects",
        examples=(
            "What projects does this person work on?",
            "What has Alice worked on?",
            "Show this person's projects",
        ),
        entity_labels=("Person",),
        cypher="""
        MATCH (person:Person)-[work:DESIGNS|IMPLEMENTED|OWNED]->(project:Project)
        WHERE toLower(person.name) = toLower($entity_0)
        RETURN project.name AS project, type(work) AS contribution,
               work.confidence AS confidence, work.strength AS strength,
               work.evidence_count AS evidence_count,
               work.contradicting_evidence_count AS contradictions
        ORDER BY project, contribution
        """,
    ),
    Intent(
        name="person_role",
        examples=(
            "What is this person's role?",
            "What position does this person have?",
        ),
        entity_labels=("Person",),
        cypher="""
        MATCH (person:Person)-[:IS]->(role:Role)
        WHERE toLower(person.name) = toLower($entity_0)
        RETURN person.name AS person, role.name AS role
        """,
    ),
    Intent(
        name="person_supervisor",
        examples=(
            "Who does this person work under?",
            "Who supervises Bob?",
            "Who is this person's manager?",
        ),
        entity_labels=("Person",),
        cypher="""
        MATCH (person:Person)-[:WORKS_UNDER]->(supervisor:Person)
        WHERE toLower(person.name) = toLower($entity_0)
        RETURN person.name AS person, supervisor.name AS supervisor
        """,
    ),
    Intent(
        name="direct_reports",
        examples=(
            "Who works under this person?",
            "Who does Alice supervise?",
            "Show this person's direct reports",
        ),
        entity_labels=("Person",),
        cypher="""
        MATCH (supervisor:Person)-[:SUPERVISES]->(person:Person)
        WHERE toLower(supervisor.name) = toLower($entity_0)
        RETURN supervisor.name AS supervisor, person.name AS direct_report
        ORDER BY direct_report
        """,
    ),
    Intent(
        name="project_contributors",
        examples=(
            "Who works on this project?",
            "Who contributed to Frontend?",
            "Who designed or implemented the project?",
            "Who knows about this project?",
            "Who has expertise in this project?",
            "Who is familiar with this project?",
        ),
        entity_labels=("Project",),
        cypher="""
        MATCH (person:Person)-[work:DESIGNS|IMPLEMENTED|OWNED]->(project:Project)
        WHERE toLower(project.name) = toLower($entity_0)
        RETURN person.name AS person, type(work) AS contribution,
               work.confidence AS confidence, work.strength AS strength,
               work.evidence_count AS evidence_count,
               work.contradicting_evidence_count AS contradictions
        ORDER BY contribution, strength DESC, person
        """,
    ),
    Intent(
        name="relationship_evidence",
        examples=(
            "Why do we think this person worked on this project?",
            "What evidence supports this person's contribution?",
            "Show the evidence connecting this person and project",
        ),
        entity_labels=("Person", "Project"),
        cypher="""
        MATCH (person:Person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(project:Project)
        WHERE toLower(person.name) = toLower($entity_0)
          AND toLower(project.name) = toLower($entity_1)
        RETURN evidence.contribution_type AS contribution,
               evidence.level AS level,
               evidence.weight AS weight,
               coalesce(evidence.polarity, 1) AS polarity,
               evidence.source AS source,
               evidence.statement AS statement,
               evidence.source_document_id AS document_id,
               evidence.inference_rule AS inference_rule
        ORDER BY weight DESC, contribution
        """,
    ),
    Intent(
        name="people_connection",
        examples=(
            "How are these two people connected?",
            "What is the relationship between Alice and Bob?",
            "How does this person relate to the other person?",
        ),
        entity_labels=("Person", "Person"),
        cypher="""
        MATCH path = shortestPath(
          (first:Person)-[*..6]-(second:Person)
        )
        WHERE toLower(first.name) = toLower($entity_0)
          AND toLower(second.name) = toLower($entity_1)
        RETURN [node IN nodes(path) | node.name] AS people_and_entities,
               [relationship IN relationships(path) | type(relationship)] AS relationships
        """,
    ),
)


def get_entities(driver) -> list[dict[str, str]]:
    records, _, _ = driver.execute_query(
        """
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN labels(n)[0] AS label, n.name AS name
        ORDER BY label, name
        """,
        database_="neo4j",
    )
    return [record.data() for record in records]


def classify_intent(question: str) -> tuple[Intent, float]:
    lowered = question.lower()
    intent_aliases = {
        "person_summary": (
            "what does",
            "tell me about",
            "summarize",
        ),
        "project_contributors": (
            "knows about",
            "know about",
            "expertise in",
            "familiar with",
        ),
        "relationship_evidence": (
            "why do we think",
            "what evidence",
            "show evidence",
            "evidence supports",
        ),
    }
    for intent_name, phrases in intent_aliases.items():
        if any(phrase in lowered for phrase in phrases):
            intent = next(intent for intent in INTENTS if intent.name == intent_name)
            return intent, 1.0

    example_to_intent = {
        example: intent
        for intent in INTENTS
        for example in intent.examples
    }
    best_match = score_semantic_matches(question, example_to_intent, limit=1)[0]
    return example_to_intent[best_match.text], best_match.confidence


def resolve_entities(
    question: str,
    required_labels: tuple[str, ...],
    entities: list[dict[str, str]],
) -> tuple[list[str], list[float]]:
    resolved = []
    confidences = []
    used_names = set()
    lowered_question = question.lower()

    for label in required_labels:
        candidates = [
            entity["name"]
            for entity in entities
            if entity["label"] == label and entity["name"] not in used_names
        ]
        if not candidates:
            raise ValueError(f"No unused {label} entities are available.")

        exact_matches = [
            name for name in candidates if name.lower() in lowered_question
        ]
        if exact_matches:
            name = max(exact_matches, key=len)
            confidence = 1.0
        else:
            match = score_semantic_matches(question, candidates, limit=1)[0]
            name = match.text
            confidence = match.confidence

        resolved.append(name)
        confidences.append(confidence)
        used_names.add(name)

    return resolved, confidences


def format_value(value: Any) -> str:
    if isinstance(value, list):
        return " -> ".join(format_value(item) for item in value)
    return str(value)


def format_result_value(key: str, value: Any) -> str:
    if key in {"confidence", "strength"} and isinstance(value, (int, float)):
        return f"{value:.1%}"
    return format_value(value)


def print_results(records) -> None:
    if not records:
        print("No matching graph data found.")
        return

    for record in records:
        values = [
            f"{key}: {format_result_value(key, value)}"
            for key, value in record.items()
        ]
        print(f"- {'; '.join(values)}")


def answer_question(question: str) -> int:
    if not question:
        print("A question is required.")
        return 1

    try:
        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            entities = get_entities(driver)
            intent, intent_confidence = classify_intent(question)
            names, entity_confidences = resolve_entities(
                question,
                intent.entity_labels,
                entities,
            )
            parameters = {
                f"entity_{index}": name for index, name in enumerate(names)
            }
            records, _, _ = driver.execute_query(
                intent.cypher,
                parameters_=parameters,
                database_="neo4j",
            )
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not query Neo4j: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Could not answer graph question: {error}", file=sys.stderr)
        return 1

    print(f"\nMatched intent: {intent.name} ({intent_confidence:.1%})")
    for label, name, confidence in zip(
        intent.entity_labels,
        names,
        entity_confidences,
    ):
        print(f"Matched {label}: {name} ({confidence:.1%})")
    print()
    print_results(records)
    return 0


def main() -> int:
    question = input("Ask a question about the graph: ").strip()
    return answer_question(question)


if __name__ == "__main__":
    raise SystemExit(main())
