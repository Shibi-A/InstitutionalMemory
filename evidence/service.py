"""Create evidence and recalculate derived contribution relationships."""

import math
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


CONTRIBUTION_TYPES = ("DESIGNS", "IMPLEMENTED", "OWNED")
EVIDENCE_WEIGHTS = {
    "explicit": 1.0,
    "inferred": 0.75,
    "aggregated": 0.5,
}
DEFAULT_HALF_LIFE_DAYS = float(os.getenv("EVIDENCE_HALF_LIFE_DAYS", "365"))


@dataclass(frozen=True)
class RelationshipScore:
    confidence: float
    strength: float
    evidence_count: int
    evidence_weight: float
    decayed_evidence_weight: float
    supporting_evidence_count: int
    contradicting_evidence_count: int
    contradicting_evidence_weight: float
    decayed_contradicting_evidence_weight: float


def calculate_confidence(total_weight: float) -> float:
    return 1.0 - math.exp(-total_weight)


def calculate_decay_multiplier(age_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        raise ValueError("Evidence half-life must be greater than zero.")
    return math.pow(0.5, max(0.0, age_days) / half_life_days)


def calculate_decayed_weight(
    weight: float,
    age_days: float,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    return weight * calculate_decay_multiplier(age_days, half_life_days)


def evidence_age_days(value, now: Optional[datetime] = None) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "to_native"):
        value = value.to_native()
    if not isinstance(value, datetime):
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current - value).total_seconds() / 86400)


def calculate_adjusted_confidence(
    supporting_weight: float,
    contradicting_weight: float,
) -> float:
    if supporting_weight <= 0:
        return 0.0
    certainty = calculate_confidence(supporting_weight)
    agreement = supporting_weight / (supporting_weight + contradicting_weight)
    return certainty * agreement


def calculate_effective_weight(
    supporting_weight: float,
    contradicting_weight: float,
) -> float:
    return max(0.0, supporting_weight - contradicting_weight)


def calculate_strength(person_weight: float, project_type_weight: float) -> float:
    if project_type_weight <= 0:
        return 0.0
    return person_weight / project_type_weight


def add_contribution_evidence(
    driver,
    *,
    person: str,
    project: str,
    contribution_type: str,
    level: str,
    source: str,
    statement: str,
    source_document_id: Optional[str] = None,
    inference_rule: Optional[str] = None,
    observed_at: Optional[str] = None,
    polarity: int = 1,
    weight: Optional[float] = None,
    evidence_id: Optional[str] = None,
    recalculate: bool = True,
) -> str:
    contribution_type = contribution_type.upper()
    if contribution_type not in CONTRIBUTION_TYPES:
        raise ValueError(f"Unsupported contribution type: {contribution_type}")
    if level not in EVIDENCE_WEIGHTS:
        raise ValueError(f"Unsupported evidence level: {level}")
    if polarity not in (-1, 1):
        raise ValueError("Evidence polarity must be 1 or -1.")

    evidence_id = evidence_id or str(uuid.uuid4())
    evidence_weight = weight if weight is not None else EVIDENCE_WEIGHTS[level]
    driver.execute_query(
        """
        MERGE (person:Person {name: $person})
        MERGE (project:Project {name: $project})
        MERGE (evidence:Evidence {id: $evidence_id})
        ON CREATE SET evidence.created_at = datetime(),
                      evidence.observed_at = CASE
                        WHEN $observed_at IS NULL THEN datetime()
                        ELSE datetime($observed_at)
                      END
        SET evidence.level = $level,
            evidence.weight = $weight,
            evidence.source = $source,
            evidence.statement = $statement,
            evidence.contribution_type = $contribution_type,
            evidence.source_document_id = $source_document_id,
            evidence.inference_rule = $inference_rule,
            evidence.polarity = $polarity
        MERGE (person)-[:HAS_EVIDENCE]->(evidence)
        MERGE (evidence)-[:ABOUT]->(project)
        """,
        person=person,
        project=project,
        evidence_id=evidence_id,
        level=level,
        weight=evidence_weight,
        source=source,
        statement=statement,
        contribution_type=contribution_type,
        source_document_id=source_document_id,
        inference_rule=inference_rule,
        observed_at=observed_at,
        polarity=polarity,
        database_="neo4j",
    )
    if recalculate:
        recalculate_relationship_scores(driver, project, contribution_type)
    return evidence_id


def recalculate_relationship_scores(
    driver,
    project: str,
    contribution_type: str,
) -> None:
    contribution_type = contribution_type.upper()
    if contribution_type not in CONTRIBUTION_TYPES:
        raise ValueError(f"Unsupported contribution type: {contribution_type}")

    evidence_records, _, _ = driver.execute_query(
        """
        MATCH (person:Person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(project:Project)
        WHERE toLower(project.name) = toLower($project)
          AND evidence.contribution_type = $contribution_type
        RETURN person.name AS person, project.name AS project,
               evidence.weight AS weight,
               coalesce(evidence.polarity, 1) AS polarity,
               coalesce(evidence.observed_at, evidence.created_at) AS observed_at
        """,
        project=project,
        contribution_type=contribution_type,
        database_="neo4j",
    )
    aggregated = {}
    for evidence in evidence_records:
        person = evidence["person"]
        record = aggregated.setdefault(
            person,
            {
                "person": person,
                "project": evidence["project"],
                "evidence_count": 0,
                "raw_supporting_weight": 0.0,
                "raw_contradicting_weight": 0.0,
                "supporting_weight": 0.0,
                "contradicting_weight": 0.0,
                "supporting_count": 0,
                "contradicting_count": 0,
            },
        )
        decayed_weight = calculate_decayed_weight(
            evidence["weight"],
            evidence_age_days(evidence["observed_at"]),
        )
        record["evidence_count"] += 1
        if evidence["polarity"] == -1:
            record["raw_contradicting_weight"] += evidence["weight"]
            record["contradicting_weight"] += decayed_weight
            record["contradicting_count"] += 1
        else:
            record["raw_supporting_weight"] += evidence["weight"]
            record["supporting_weight"] += decayed_weight
            record["supporting_count"] += 1
    records = list(aggregated.values())
    effective_weights = {
        record["person"]: calculate_effective_weight(
            record["supporting_weight"],
            record["contradicting_weight"],
        )
        for record in records
    }
    total_weight = sum(effective_weights.values())

    driver.execute_query(
        f"""
        MATCH (:Person)-[work:{contribution_type}]->(project:Project)
        WHERE toLower(project.name) = toLower($project)
        DELETE work
        """,
        project=project,
        database_="neo4j",
    )

    for record in records:
        if record["supporting_weight"] <= 0:
            continue
        score = RelationshipScore(
            confidence=calculate_adjusted_confidence(
                record["supporting_weight"],
                record["contradicting_weight"],
            ),
            strength=calculate_strength(
                effective_weights[record["person"]],
                total_weight,
            ),
            evidence_count=record["evidence_count"],
            evidence_weight=record["raw_supporting_weight"],
            decayed_evidence_weight=record["supporting_weight"],
            supporting_evidence_count=record["supporting_count"],
            contradicting_evidence_count=record["contradicting_count"],
            contradicting_evidence_weight=record["raw_contradicting_weight"],
            decayed_contradicting_evidence_weight=record["contradicting_weight"],
        )
        driver.execute_query(
            f"""
            MATCH (person:Person), (project:Project)
            WHERE toLower(person.name) = toLower($person)
              AND toLower(project.name) = toLower($project)
            MERGE (person)-[work:{contribution_type}]->(project)
            SET work.confidence = $confidence,
                work.strength = $strength,
                work.evidence_count = $evidence_count,
                work.evidence_weight = $evidence_weight,
                work.decayed_evidence_weight = $decayed_evidence_weight,
                work.evidence_half_life_days = $evidence_half_life_days,
                work.supporting_evidence_count = $supporting_evidence_count,
                work.contradicting_evidence_count = $contradicting_evidence_count,
                work.contradicting_evidence_weight = $contradicting_evidence_weight,
                work.decayed_contradicting_evidence_weight =
                  $decayed_contradicting_evidence_weight,
                work.last_calculated_at = datetime()
            """,
            person=record["person"],
            project=record["project"],
            confidence=score.confidence,
            strength=score.strength,
            evidence_count=score.evidence_count,
            evidence_weight=score.evidence_weight,
            decayed_evidence_weight=score.decayed_evidence_weight,
            evidence_half_life_days=DEFAULT_HALF_LIFE_DAYS,
            supporting_evidence_count=score.supporting_evidence_count,
            contradicting_evidence_count=score.contradicting_evidence_count,
            contradicting_evidence_weight=score.contradicting_evidence_weight,
            decayed_contradicting_evidence_weight=(
                score.decayed_contradicting_evidence_weight
            ),
            database_="neo4j",
        )


def remove_contribution_evidence(
    driver,
    *,
    person: str,
    project: str,
    contribution_type: Optional[str] = None,
) -> int:
    contribution_types = (
        (contribution_type.upper(),)
        if contribution_type
        else CONTRIBUTION_TYPES
    )
    if any(value not in CONTRIBUTION_TYPES for value in contribution_types):
        raise ValueError("Unsupported contribution type.")

    records, _, _ = driver.execute_query(
        """
        MATCH (person:Person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(project:Project)
        WHERE toLower(person.name) = toLower($person)
          AND toLower(project.name) = toLower($project)
          AND evidence.contribution_type IN $contribution_types
        RETURN evidence.id AS evidence_id,
               evidence.contribution_type AS contribution_type
        """,
        person=person,
        project=project,
        contribution_types=list(contribution_types),
        database_="neo4j",
    )
    driver.execute_query(
        """
        MATCH (person:Person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(project:Project)
        WHERE toLower(person.name) = toLower($person)
          AND toLower(project.name) = toLower($project)
          AND evidence.contribution_type IN $contribution_types
        DETACH DELETE evidence
        """,
        person=person,
        project=project,
        contribution_types=list(contribution_types),
        database_="neo4j",
    )
    for value in contribution_types:
        recalculate_relationship_scores(driver, project, value)
    return len(records)


def remove_document_evidence(driver, document_id: str) -> int:
    records, _, _ = driver.execute_query(
        """
        MATCH (evidence:Evidence {source_document_id: $document_id})-[:ABOUT]->(project:Project)
        RETURN DISTINCT project.name AS project,
               evidence.contribution_type AS contribution_type,
               count(evidence) AS evidence_count
        """,
        document_id=document_id,
        database_="neo4j",
    )
    removed_count = sum(record["evidence_count"] for record in records)
    driver.execute_query(
        """
        MATCH (evidence:Evidence {source_document_id: $document_id})
        DETACH DELETE evidence
        """,
        document_id=document_id,
        database_="neo4j",
    )
    driver.execute_query(
        "MATCH (document:Document {id: $document_id}) DETACH DELETE document",
        document_id=document_id,
        database_="neo4j",
    )
    for record in records:
        recalculate_relationship_scores(
            driver,
            record["project"],
            record["contribution_type"],
        )
    return removed_count


def backfill_existing_contributions(driver) -> int:
    records, _, _ = driver.execute_query(
        """
        MATCH (person:Person)-[work:DESIGNS|IMPLEMENTED|OWNED]->(project:Project)
        WHERE work.evidence_count IS NULL
        RETURN person.name AS person, type(work) AS contribution_type,
               project.name AS project
        """,
        database_="neo4j",
    )
    score_groups = set()
    for record in records:
        evidence_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    f"legacy_graph:{record['person']}:"
                    f"{record['contribution_type']}:{record['project']}"
                ),
            )
        )
        add_contribution_evidence(
            driver,
            person=record["person"],
            project=record["project"],
            contribution_type=record["contribution_type"],
            level="explicit",
            source="legacy_graph",
            statement="Backfilled from an existing graph relationship.",
            evidence_id=evidence_id,
            recalculate=False,
        )
        score_groups.add((record["project"], record["contribution_type"]))
    for project, contribution_type in score_groups:
        recalculate_relationship_scores(driver, project, contribution_type)
    return len(records)
