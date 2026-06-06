"""Route general user input to graph retrieval or controlled graph updates."""

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.graph_query import answer_question
from retrieval.graph_update import apply_update


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


def handle_input(user_input: str) -> int:
    if not user_input:
        print("A graph question or update is required.")
        return 1

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
