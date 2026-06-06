"""Remove an ingested document and its evidence from Neo4j."""

import os
import sys

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from evidence.service import remove_document_evidence


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m ingestion.document_remove <document-id>")
        return 1

    document_id = sys.argv[1]
    try:
        with GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "password"),
            ),
        ) as driver:
            removed = remove_document_evidence(driver, document_id)
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not remove document: {error}", file=sys.stderr)
        return 1

    print(f"Removed document {document_id} and {removed} evidence record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
