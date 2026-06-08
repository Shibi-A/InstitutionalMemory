"""Route general user input to graph retrieval or controlled graph updates."""

import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.graph_query import answer_question
from retrieval.graph_update import apply_update
from retrieval.graph_feedback import apply_feedback
from ingestion.batch_ingest import ingest_directory
from ingestion.github_repository_ingest import ingest_github_repository
from ingestion.github_client import parse_github_repository


QUERY_PREFIXES = (
    "am ",
    "can you show",
    "are ",
    "could ",
    "did ",
    "do ",
    "does ",
    "how ",
    "is ",
    "list ",
    "show ",
    "tell me ",
    "what ",
    "when ",
    "where ",
    "which ",
    "who ",
    "why ",
    "would ",
)


def classify_operation(user_input: str) -> tuple[str, float]:
    lowered = user_input.lower()
    if lowered.startswith(QUERY_PREFIXES) or lowered.endswith("?"):
        return "query", 1.0
    return "update", 1.0


def extract_github_repository(user_input: str):
    match = re.search(
        r"(https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?)",
        user_input,
        re.IGNORECASE,
    )
    if match:
        return parse_github_repository(match.group(1)).full_name
    match = re.match(
        r"^\s*ingest\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?)\s*$",
        user_input,
        re.IGNORECASE,
    )
    return parse_github_repository(match.group(1)).full_name if match else None


def handle_input(user_input: str) -> int:
    if not user_input:
        print("A graph question or update is required.")
        return 1

    lowered = user_input.lower()
    if lowered.startswith("no "):
        print("Matched operation: feedback (100.0%)")
        return apply_feedback(user_input)
    repository = extract_github_repository(user_input)
    if "ingest" in lowered and repository:
        print("Matched operation: github_repository_ingest (100.0%)")
        return ingest_github_repository(repository)
    if (
        "ingest" in lowered
        and ("everything" in lowered or "all" in lowered)
        and ("sample document" in lowered or "sample_docs" in lowered)
    ):
        print("Matched operation: batch_ingest (100.0%)")
        return ingest_directory(Path("sample_docs"))

    operation, confidence = classify_operation(user_input)
    print(f"Matched operation: {operation} ({confidence:.1%})")
    if operation == "update":
        return apply_update(user_input)
    return answer_question(user_input)


def main() -> int:
    print('Enter graph questions or updates. Type "quit" to exit.')
    while True:
        try:
            user_input = input("\ngraph> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0

        if user_input.lower() == "quit":
            print("Goodbye.")
            return 0
        if not user_input:
            continue

        handle_input(user_input)


if __name__ == "__main__":
    raise SystemExit(main())
