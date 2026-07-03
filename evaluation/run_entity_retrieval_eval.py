"""Compare cosine-only and BM25-plus-cosine entity retrieval."""

import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.dataset import load_cases
from scoring.hybrid_search import CosineRetriever, HybridRetriever, SearchDocument


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "search_cases.jsonl"
CATALOG_PATH = ROOT / "entity_catalog.jsonl"


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluable_cases(cases: list[dict]) -> list[dict]:
    return [
        case
        for case in cases
        if len(case["expected"].get("entities", [])) == 1
        and case["expected"]["operation"] != "abstain"
    ]


def evaluate(cases: list[dict], catalog: list[dict]) -> dict:
    by_label = defaultdict(list)
    for entity in catalog:
        by_label[entity["label"]].append(
            SearchDocument(entity["name"], entity["text"])
        )
    retrievers = {
        label: {
            "cosine": CosineRetriever(documents),
            "hybrid": HybridRetriever(documents),
        }
        for label, documents in by_label.items()
    }

    results = []
    for case in evaluable_cases(cases):
        expected = case["expected"]["entities"][0]
        case_result = {
            "id": case["id"],
            "split": case["split"],
            "tags": case["tags"],
            "expected": expected["name"],
        }
        for strategy, retriever in retrievers[expected["label"]].items():
            ranking = retriever.score(case["query"], limit=3)
            keys = [match.key for match in ranking]
            case_result[strategy] = {
                "top_1": bool(keys and keys[0] == expected["name"]),
                "recall_at_3": expected["name"] in keys,
                "ranking": keys,
            }
        results.append(case_result)
    return {"cases": results}


def summarize(results: dict) -> None:
    cases = results["cases"]
    print(f"Evaluated single-entity cases: {len(cases)}")
    print()
    for strategy in ("cosine", "hybrid"):
        top_1 = sum(case[strategy]["top_1"] for case in cases)
        recall_at_3 = sum(case[strategy]["recall_at_3"] for case in cases)
        print(
            f"{strategy:>8}: top-1={top_1 / len(cases):.1%} "
            f"recall@3={recall_at_3 / len(cases):.1%}"
        )

    print("\nBy split:")
    splits = sorted({case["split"] for case in cases})
    for split in splits:
        split_cases = [case for case in cases if case["split"] == split]
        values = []
        for strategy in ("cosine", "hybrid"):
            correct = sum(case[strategy]["top_1"] for case in split_cases)
            values.append(f"{strategy}={correct / len(split_cases):.1%}")
        print(f"- {split}: {', '.join(values)} ({len(split_cases)} cases)")

    changes = Counter()
    print("\nChanged top-1 outcomes:")
    for case in cases:
        cosine_correct = case["cosine"]["top_1"]
        hybrid_correct = case["hybrid"]["top_1"]
        if cosine_correct == hybrid_correct:
            continue
        outcome = "improved" if hybrid_correct else "regressed"
        changes[outcome] += 1
        print(
            f"- {outcome}: {case['id']} expected={case['expected']!r} "
            f"cosine={case['cosine']['ranking'][:1]} "
            f"hybrid={case['hybrid']['ranking'][:1]}"
        )
    if not changes:
        print("- none")


def main() -> int:
    results = evaluate(load_cases(CASES_PATH), load_catalog())
    summarize(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
