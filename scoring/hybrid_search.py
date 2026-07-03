"""Rank searchable documents with BM25, cosine similarity, and rank fusion."""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import uuid4

import chromadb
from chromadb.config import Settings


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class SearchDocument:
    key: str
    text: str


@dataclass(frozen=True)
class RankedDocument:
    key: str
    score: float


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


class BM25Retriever:
    def __init__(
        self,
        documents: Iterable[SearchDocument],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.documents = list(documents)
        if not self.documents:
            raise ValueError("At least one search document is required.")
        self.k1 = k1
        self.b = b
        self.tokens = [tokenize(document.text) for document in self.documents]
        self.term_frequencies = [Counter(tokens) for tokens in self.tokens]
        self.average_length = sum(map(len, self.tokens)) / len(self.tokens)
        self.document_frequencies = Counter(
            token
            for tokens in self.tokens
            for token in set(tokens)
        )

    def score(self, query: str, limit: Optional[int] = None) -> list[RankedDocument]:
        query_tokens = set(tokenize(query))
        ranked = []
        for document, frequencies, tokens in zip(
            self.documents,
            self.term_frequencies,
            self.tokens,
        ):
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if not frequency:
                    continue
                document_frequency = self.document_frequencies[token]
                inverse_document_frequency = math.log(
                    1
                    + (
                        len(self.documents) - document_frequency + 0.5
                    )
                    / (document_frequency + 0.5)
                )
                length_normalization = (
                    1
                    - self.b
                    + self.b * len(tokens) / max(1.0, self.average_length)
                )
                score += inverse_document_frequency * (
                    frequency * (self.k1 + 1)
                    / (frequency + self.k1 * length_normalization)
                )
            if score > 0:
                ranked.append(RankedDocument(document.key, score))
        ranked.sort(key=lambda match: (-match.score, match.key))
        return ranked[:limit] if limit else ranked


class CosineRetriever:
    def __init__(self, documents: Iterable[SearchDocument]) -> None:
        self.documents = list(documents)
        if not self.documents:
            raise ValueError("At least one search document is required.")
        client = chromadb.Client(
            Settings(anonymized_telemetry=False, is_persistent=False)
        )
        self.collection = client.create_collection(
            name=f"hybrid_search_{uuid4().hex}",
            metadata={"hnsw:space": "cosine"},
        )
        self.collection.add(
            ids=[document.key for document in self.documents],
            documents=[document.text for document in self.documents],
        )

    def score(self, query: str, limit: Optional[int] = None) -> list[RankedDocument]:
        result_count = min(limit or len(self.documents), len(self.documents))
        results = self.collection.query(query_texts=[query], n_results=result_count)
        return [
            RankedDocument(key, max(0.0, min(1.0, 1.0 - distance)))
            for key, distance in zip(results["ids"][0], results["distances"][0])
        ]


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[RankedDocument]],
    *,
    rank_constant: int = 60,
    limit: Optional[int] = None,
) -> list[RankedDocument]:
    scores = Counter()
    for ranking in rankings:
        for rank, match in enumerate(ranking, 1):
            scores[match.key] += 1.0 / (rank_constant + rank)
    fused = [
        RankedDocument(key, score)
        for key, score in scores.items()
    ]
    fused.sort(key=lambda match: (-match.score, match.key))
    return fused[:limit] if limit else fused


class HybridRetriever:
    def __init__(self, documents: Iterable[SearchDocument]) -> None:
        documents = list(documents)
        self.bm25 = BM25Retriever(documents)
        self.cosine = CosineRetriever(documents)

    def score(self, query: str, limit: Optional[int] = None) -> list[RankedDocument]:
        return reciprocal_rank_fusion(
            (
                self.cosine.score(query),
                self.bm25.score(query),
            ),
            limit=limit,
        )
