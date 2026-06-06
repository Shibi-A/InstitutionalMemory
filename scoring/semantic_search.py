"""Score text similarity with Chroma vector embeddings."""

from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import uuid4

import chromadb
from chromadb.config import Settings


@dataclass(frozen=True)
class SemanticMatch:
    text: str
    confidence: float


def score_semantic_matches(
    user_input: str,
    candidates: Iterable[str],
    limit: Optional[int] = None,
) -> list[SemanticMatch]:
    """Return candidate strings ordered by semantic similarity."""
    texts = list(dict.fromkeys(candidates))
    if not texts:
        raise ValueError("At least one candidate is required.")

    client = chromadb.Client(
        Settings(anonymized_telemetry=False, is_persistent=False)
    )
    collection = client.create_collection(
        name=f"project_name_search_{uuid4().hex}",
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[str(index) for index in range(len(texts))],
        documents=texts,
    )

    result_count = min(limit or len(texts), len(texts))
    results = collection.query(query_texts=[user_input], n_results=result_count)
    matched_texts = results["documents"][0]
    cosine_distances = results["distances"][0]

    return [
        SemanticMatch(
            text=text,
            confidence=max(0.0, min(1.0, 1.0 - distance)),
        )
        for text, distance in zip(matched_texts, cosine_distances)
    ]


def main():
    candidates = [
        "API Integration",
        "Backend",
        "Frontend",
        "UI",
        "Project Management",
    ]
    user_input = input("Enter a project description: ").strip()
    if not user_input:
        print("A project description is required.")
        return 1

    matches = score_semantic_matches(user_input, candidates)
    print("Semantic scores:")
    for match in matches:
        print(f"- {match.text}: {match.confidence:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
