"""Apply user corrections as supporting and contradictory evidence."""

import os
import re
import sys
from dataclasses import dataclass

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from evidence.service import add_contribution_evidence


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


@dataclass(frozen=True)
class Correction:
    correct_person: str
    incorrect_person: str
    project: str
    contribution_type: str


def parse_correction(text: str) -> Correction:
    match = re.match(
        r"^\s*no[, ]+\s*(.+?)\s+"
        r"(built|buit|created|designed|developed|implemented|owns?|owned)\s+"
        r"(?:the\s+)?(.+?)\s+not\s+(.+?)\s*[.!]?\s*$",
        text,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            'Use a correction like: "no Alice built Compilation Service not Bob".'
        )

    relationship_types = {
        "built": "IMPLEMENTED",
        "buit": "IMPLEMENTED",
        "created": "IMPLEMENTED",
        "designed": "DESIGNS",
        "developed": "IMPLEMENTED",
        "implemented": "IMPLEMENTED",
        "own": "OWNED",
        "owns": "OWNED",
        "owned": "OWNED",
    }
    return Correction(
        correct_person=match.group(1).strip().title(),
        contribution_type=relationship_types[match.group(2).lower()],
        project=match.group(3).strip().title(),
        incorrect_person=match.group(4).strip().title(),
    )


def apply_feedback(text: str) -> int:
    try:
        correction = parse_correction(text)
        print(
            "\nProposed correction:\n"
            f'- support {correction.correct_person} '
            f'-[:{correction.contribution_type}]-> {correction.project}\n'
            f'- contradict {correction.incorrect_person} '
            f'-[:{correction.contribution_type}]-> {correction.project}'
        )
        if input("Apply this feedback? [y/N]: ").strip().lower() != "y":
            print("Feedback cancelled. No changes were made.")
            return 0

        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            add_contribution_evidence(
                driver,
                person=correction.correct_person,
                project=correction.project,
                contribution_type=correction.contribution_type,
                level="explicit",
                source="user_feedback",
                statement=text,
                polarity=1,
                recalculate=False,
            )
            add_contribution_evidence(
                driver,
                person=correction.incorrect_person,
                project=correction.project,
                contribution_type=correction.contribution_type,
                level="explicit",
                source="user_feedback",
                statement=text,
                polarity=-1,
            )
    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Could not apply feedback: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Could not parse feedback: {error}", file=sys.stderr)
        return 1

    print("Feedback acknowledged and relationship scores recalculated.")
    return 0
