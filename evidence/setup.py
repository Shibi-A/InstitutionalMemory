"""Create Neo4j constraints used by evidence-backed ingestion."""

import os

from neo4j import GraphDatabase


def main() -> None:
    queries = (
        """
        CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS
        FOR (evidence:Evidence) REQUIRE evidence.id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT document_id_unique IF NOT EXISTS
        FOR (document:Document) REQUIRE document.id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT repository_full_name_unique IF NOT EXISTS
        FOR (repository:Repository) REQUIRE repository.full_name IS UNIQUE
        """,
        """
        CREATE CONSTRAINT commit_repository_sha_unique IF NOT EXISTS
        FOR (commit:Commit) REQUIRE (commit.repository, commit.sha) IS UNIQUE
        """,
    )
    with GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "password"),
        ),
    ) as driver:
        for query in queries:
            driver.execute_query(query, database_="neo4j")
    print("Evidence schema constraints are ready.")


if __name__ == "__main__":
    main()
