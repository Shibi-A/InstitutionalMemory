"""Ingest structured documents and create evidence-backed graph inferences."""

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evidence.service import add_contribution_evidence


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    owner: str
    subject: str
    content: str


@dataclass(frozen=True)
class ProposedEvidence:
    person: str
    project: str
    contribution_type: str
    level: str
    weight: float
    statement: str
    inference_rule: Optional[str] = None


def parse_document(text: str) -> Document:
    fields = {}
    content_lines = []
    in_content = False

    for line in text.splitlines():
        match = re.match(r"^(Title|Owner|Subject):\s*(.+)$", line.strip(), re.IGNORECASE)
        if match and not in_content:
            fields[match.group(1).lower()] = match.group(2).strip()
        else:
            in_content = True
            content_lines.append(line)

    missing = [field for field in ("owner", "subject") if not fields.get(field)]
    if missing:
        raise ValueError(f"Document is missing required field(s): {', '.join(missing)}")

    normalized = text.strip().encode("utf-8")
    document_id = hashlib.sha256(normalized).hexdigest()[:16]
    return Document(
        document_id=document_id,
        title=fields.get("title", fields["subject"]),
        owner=fields["owner"],
        subject=fields["subject"],
        content="\n".join(content_lines).strip(),
    )


def infer_evidence(document: Document) -> list[ProposedEvidence]:
    proposed = [
        ProposedEvidence(
            person=document.owner,
            project=document.subject,
            contribution_type="DESIGNS",
            level="inferred",
            weight=0.75,
            statement=f"{document.owner} owns a document about {document.subject}.",
            inference_rule="document_owner_subject",
        )
    ]
    explicit_pattern = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+"
        r"(authored|built|designed|developed|implemented|led|owns?|owned)\s+"
        r"(.+?)(?=[.!?\n]|$)"
    )
    relationship_types = {
        "authored": "DESIGNS",
        "designed": "DESIGNS",
        "implemented": "IMPLEMENTED",
        "built": "IMPLEMENTED",
        "developed": "IMPLEMENTED",
        "led": "OWNED",
        "own": "OWNED",
        "owns": "OWNED",
        "owned": "OWNED",
    }
    for match in explicit_pattern.finditer(document.content):
        statement = match.group(0).strip()
        object_text = re.sub(r"^the\s+", "", match.group(3).strip(), flags=re.IGNORECASE)
        named_targets = re.findall(
            r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\b",
            object_text,
        )
        project = (
            named_targets[0]
            if named_targets and named_targets[0] not in {"RFC"}
            else document.subject
        )
        proposed.append(
            ProposedEvidence(
                person=match.group(1).strip(),
                project=project,
                contribution_type=relationship_types[match.group(2).lower()],
                level="explicit",
                weight=1.0,
                statement=statement,
            )
        )
    return proposed


def document_exists(driver, document_id: str) -> bool:
    records, _, _ = driver.execute_query(
        "MATCH (document:Document {id: $document_id}) RETURN count(document) AS count",
        document_id=document_id,
        database_="neo4j",
    )
    return records[0]["count"] > 0


def ingest_document(driver, document: Document, proposed: list[ProposedEvidence]) -> None:
    driver.execute_query(
        """
        MERGE (document:Document {id: $document_id})
        SET document.title = $title,
            document.owner = $owner,
            document.subject = $subject,
            document.content = $content,
            document.ingested_at = datetime()
        MERGE (owner:Person {name: $owner})
        MERGE (subject:Project {name: $subject})
        MERGE (owner)-[:AUTHORED]->(document)
        MERGE (document)-[:ABOUT]->(subject)
        """,
        document_id=document.document_id,
        title=document.title,
        owner=document.owner,
        subject=document.subject,
        content=document.content,
        database_="neo4j",
    )
    for evidence in proposed:
        add_contribution_evidence(
            driver,
            person=evidence.person,
            project=evidence.project,
            contribution_type=evidence.contribution_type,
            level=evidence.level,
            weight=evidence.weight,
            source="document_ingestion",
            source_document_id=document.document_id,
            inference_rule=evidence.inference_rule,
            statement=evidence.statement,
        )


def read_document_input(path: Optional[str]) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")

    print('Paste the document below. Enter "END" on its own line when finished.')
    lines = []
    while True:
        line = input()
        if line == "END":
            return "\n".join(lines)
        lines.append(line)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        document = parse_document(read_document_input(path))
        proposed = infer_evidence(document)
        print(f"\nDocument: {document.title} ({document.document_id})")
        print("Proposed evidence:")
        for evidence in proposed:
            rule = f", rule={evidence.inference_rule}" if evidence.inference_rule else ""
            print(
                f"- {evidence.person} -[:{evidence.contribution_type}]-> "
                f"{evidence.project} ({evidence.level}, weight={evidence.weight}{rule})"
            )
        if input("Ingest this document? [y/N]: ").strip().lower() != "y":
            print("Document ingestion cancelled.")
            return 0

        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            if document_exists(driver, document.document_id):
                print("This exact document has already been ingested.")
                return 0
            ingest_document(driver, document, proposed)
    except (OSError, ValueError) as error:
        print(f"Could not parse document: {error}", file=sys.stderr)
        return 1
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not ingest document: {error}", file=sys.stderr)
        return 1

    print("Document ingestion acknowledged and completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
