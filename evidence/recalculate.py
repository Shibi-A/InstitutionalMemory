"""Refresh all derived relationship scores using current evidence ages."""

import os
import sys

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evidence.service import recalculate_relationship_scores, recalculate_skill_scores


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def refresh_all_relationship_scores(driver) -> int:
    driver.execute_query(
        """
        MATCH (evidence:Evidence)
        WHERE evidence.observed_at IS NULL
        SET evidence.observed_at = coalesce(evidence.created_at, datetime())
        """,
        database_="neo4j",
    )
    records, _, _ = driver.execute_query(
        """
        MATCH (:Person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(project:Project)
        WHERE evidence.contribution_type IS NOT NULL
        RETURN DISTINCT project.name AS project,
               evidence.contribution_type AS contribution_type
        """,
        database_="neo4j",
    )
    for record in records:
        recalculate_relationship_scores(
            driver,
            record["project"],
            record["contribution_type"],
        )
    skill_records, _, _ = driver.execute_query(
        """
        MATCH (:Person)-[:HAS_EVIDENCE]->(evidence:Evidence)-[:ABOUT]->(skill:Skill)
        WHERE evidence.evidence_type = 'skill'
        RETURN DISTINCT skill.name AS skill
        """,
        database_="neo4j",
    )
    for record in skill_records:
        recalculate_skill_scores(driver, record["skill"])
    return len(records) + len(skill_records)


def main() -> int:
    try:
        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            refreshed = refresh_all_relationship_scores(driver)
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not refresh relationship scores: {error}", file=sys.stderr)
        return 1

    print(f"Refreshed {refreshed} project/contribution score groups.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
