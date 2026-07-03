"""Handle read-only graph retrieval using local hybrid intent matching."""

import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable

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


@dataclass(frozen=True)
class OwnershipCandidate:
    person: str
    score: float
    likelihood: float
    direct_owner: bool
    criteria: tuple[str, ...]


OWNERSHIP_WEIGHTS = {
    "OWNED": 1.0,
    "DESIGNS": 0.75,
    "IMPLEMENTED": 0.55,
}


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
        OPTIONAL MATCH (person)-[skillRelationship:HAS_SKILL]->(skill:Skill)
        RETURN person.name AS person,
               collect(DISTINCT role.name) AS roles,
               collect(DISTINCT project.name) AS projects,
               collect(DISTINCT type(work)) AS contributions,
               collect(DISTINCT skill.name) AS skills,
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
        cypher="",
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
        name="skill_experts",
        examples=(
            "Who knows how to use this technology?",
            "Who has this skill?",
            "Who is skilled in Python?",
            "Who has experience with Neo4j?",
        ),
        entity_labels=("Skill",),
        cypher="""
        MATCH (person:Person)-[relationship:HAS_SKILL]->(skill:Skill)
        WHERE toLower(skill.name) = toLower($entity_0)
        RETURN person.name AS person, skill.name AS skill,
               relationship.confidence AS confidence,
               relationship.strength AS strength,
               relationship.evidence_count AS evidence_count
        ORDER BY strength DESC, confidence DESC, person
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
               evidence.inference_rule AS inference_rule,
               coalesce(evidence.observed_at, evidence.created_at) AS observed_at
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


def rank_ownership_candidates(rows: Iterable[dict]) -> list[OwnershipCandidate]:
    candidates = {}
    for row in rows:
        contribution = row["contribution"]
        confidence = row.get("confidence") or 0.0
        strength = row.get("strength")
        strength = 1.0 if strength is None else strength
        score = OWNERSHIP_WEIGHTS[contribution] * confidence * strength
        person = row["person"]
        candidate = candidates.setdefault(
            person,
            {"score": 0.0, "direct_owner": False, "criteria": []},
        )
        candidate["score"] += score
        candidate["direct_owner"] = candidate["direct_owner"] or contribution == "OWNED"
        candidate["criteria"].append(
            f"{person} {contribution.lower()} the project "
            f"(recency-adjusted confidence {confidence:.1%}, strength {strength:.1%})"
        )
        for statement in row.get("statements") or []:
            if statement and statement != "Backfilled from an existing graph relationship.":
                candidate["criteria"].append(f'Evidence: "{statement}"')

    direct_candidates = {
        person: candidate
        for person, candidate in candidates.items()
        if candidate["direct_owner"]
    }
    ranked_pool = direct_candidates or candidates
    total_score = sum(candidate["score"] for candidate in ranked_pool.values())
    ranked = [
        OwnershipCandidate(
            person=person,
            score=candidate["score"],
            likelihood=(candidate["score"] / total_score if total_score else 0.0),
            direct_owner=candidate["direct_owner"],
            criteria=tuple(dict.fromkeys(candidate["criteria"])),
        )
        for person, candidate in ranked_pool.items()
    ]
    return sorted(ranked, key=lambda candidate: candidate.score, reverse=True)


def answer_project_owner(driver, project: str) -> None:
    records, _, _ = driver.execute_query(
        """
        MATCH (person:Person)-[work:DESIGNS|IMPLEMENTED|OWNED]->(project:Project)
        WHERE toLower(project.name) = toLower($project)
        OPTIONAL MATCH (person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(project)
        WHERE evidence.contribution_type = type(work)
        RETURN person.name AS person,
               type(work) AS contribution,
               work.confidence AS confidence,
               work.strength AS strength,
               collect(DISTINCT evidence.statement) AS statements
        """,
        project=project,
        database_="neo4j",
    )
    candidates = rank_ownership_candidates([record.data() for record in records])
    if not candidates:
        print("No ownership or contribution evidence found.")
        return

    owner = candidates[0]
    conclusion = "directly supported owner" if owner.direct_owner else "likely owner"
    print(f"{conclusion.title()}: {owner.person}")
    print(f"Relative ownership likelihood: {owner.likelihood:.1%}")
    print("Supporting criteria:")
    for criterion in owner.criteria:
        print(f"- {criterion}")

    alternatives = [candidate for candidate in candidates[1:] if candidate.score > 0]
    if alternatives:
        print("Other candidates considered:")
        for candidate in alternatives:
            print(f"- {candidate.person}: {candidate.likelihood:.1%}")


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
        "project_owner": (
            "who owns",
            "who is responsible for",
            "who's responsible for",
        ),
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
        "skill_experts": (
            "who has skill",
            "who has experience with",
            "who knows how to use",
            "who is skilled in",
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
            hint = extract_entity_hint(question, label)
            lexical_matches = [
                (
                    candidate,
                    SequenceMatcher(None, hint.lower(), candidate.lower()).ratio(),
                )
                for candidate in candidates
            ]
            lexical_name, lexical_confidence = max(
                lexical_matches,
                key=lambda value: value[1],
            )
            if lexical_confidence >= 0.65:
                name = lexical_name
                confidence = lexical_confidence
            else:
                match = score_semantic_matches(hint, candidates, limit=1)[0]
                name = match.text
                confidence = match.confidence
                if confidence < 0.2:
                    raise ValueError(
                        f'Could not confidently match a {label} from "{hint}".'
                    )

        resolved.append(name)
        confidences.append(confidence)
        used_names.add(name)

    return resolved, confidences


def extract_entity_hint(question: str, label: str) -> str:
    if label != "Project":
        return question

    patterns = (
        r"\b(?:owns?|responsible for)\s+(.+?)[?.!]*$",
        r"\b(?:about|on|for)\s+(.+?)[?.!]*$",
    )
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return question


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
            if intent.name == "project_owner":
                print(f"\nMatched intent: {intent.name} ({intent_confidence:.1%})")
                print(f"Matched Project: {names[0]} ({entity_confidences[0]:.1%})")
                print()
                answer_project_owner(driver, names[0])
                return 0
            else:
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
