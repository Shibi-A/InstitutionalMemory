"""Ingest every new single-document text file in a directory."""

import os
import sys
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from ingestion.document_ingest import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    document_exists,
    infer_evidence,
    ingest_document,
    parse_document,
)


def load_documents(directory: Path):
    documents = []
    errors = []
    for path in sorted(directory.glob("*.txt")):
        try:
            documents.append((path, parse_document(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as error:
            errors.append((path, error))
    return documents, errors


def ingest_directory(directory: Path) -> int:
    if not directory.is_dir():
        print(f"Document directory does not exist: {directory}", file=sys.stderr)
        return 1

    documents, errors = load_documents(directory)
    for path, error in errors:
        print(f"Skipping {path}: {error}", file=sys.stderr)
    if not documents:
        print(f"No valid .txt documents found in {directory}.")
        return 1

    print(f"Found {len(documents)} valid document(s) in {directory}:")
    for path, document in documents:
        print(f"- {path.name}: {document.title} ({document.owner} -> {document.subject})")

    if input("Ingest every new document in this batch? [y/N]: ").strip().lower() != "y":
        print("Batch ingestion cancelled.")
        return 0

    try:
        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            ingested = 0
            skipped = 0
            for path, document in documents:
                if document_exists(driver, document.document_id):
                    print(f"Skipping already-ingested document: {path.name}")
                    skipped += 1
                    continue
                proposed = infer_evidence(document)
                ingest_document(driver, document, proposed)
                print(f"Ingested {path.name}: {len(proposed)} evidence record(s)")
                ingested += 1
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not ingest document batch: {error}", file=sys.stderr)
        return 1

    print(f"Batch ingestion completed: ingested={ingested}, skipped={skipped}.")
    return 0


def main() -> int:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_docs")
    return ingest_directory(directory)


if __name__ == "__main__":
    raise SystemExit(main())
