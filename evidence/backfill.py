"""Backfill existing contribution relationships with evidence nodes."""

import os

from neo4j import GraphDatabase

from evidence.service import backfill_existing_contributions


def main() -> None:
    with GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "password"),
        ),
    ) as driver:
        count = backfill_existing_contributions(driver)
    print(f"Backfilled {count} contribution relationship(s).")


if __name__ == "__main__":
    main()
