"""Rank text with hybrid BM25 and Chroma cosine retrieval."""

from dataclasses import dataclass
from typing import Iterable, Optional

from scoring.hybrid_search import (
    BM25Retriever,
    CosineRetriever,
    SearchDocument,
    reciprocal_rank_fusion,
)


@dataclass(frozen=True)
class SemanticMatch:
    text: str
    confidence: float


def score_semantic_matches(
    user_input: str,
    candidates: Iterable[str],
    limit: Optional[int] = None,
) -> list[SemanticMatch]:
    """Return candidate strings ordered by BM25-plus-cosine rank fusion."""
    texts = list(dict.fromkeys(candidates))
    if not texts:
        raise ValueError("At least one candidate is required.")

    documents = [
        SearchDocument(str(index), text)
        for index, text in enumerate(texts)
    ]
    cosine_matches = CosineRetriever(documents).score(user_input)
    bm25_matches = BM25Retriever(documents).score(user_input)
    fused_matches = reciprocal_rank_fusion(
        (cosine_matches, bm25_matches),
        limit=min(limit or len(texts), len(texts)),
    )
    cosine_scores = {match.key: match.score for match in cosine_matches}

    return [
        SemanticMatch(
            text=texts[int(match.key)],
            confidence=cosine_scores[match.key],
        )
        for match in fused_matches
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
    print("Hybrid semantic rankings with cosine scores:")
    for match in matches:
        print(f"- {match.text}: {match.confidence:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
