import unittest
from collections import Counter
from pathlib import Path

from evaluation.dataset import load_cases, validate_cases


DATASET_PATH = Path("evaluation/search_cases.jsonl")


class EvaluationDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(DATASET_PATH)

    def test_dataset_has_all_splits(self):
        splits = Counter(case["split"] for case in self.cases)

        self.assertGreaterEqual(splits["development"], 15)
        self.assertGreaterEqual(splits["test"], 15)
        self.assertGreaterEqual(splits["regression"], 5)

    def test_dataset_covers_core_operations(self):
        operations = {
            case["expected"]["operation"]
            for case in self.cases
        }

        self.assertEqual(
            operations,
            {"query", "update", "feedback", "ingestion", "abstain"},
        )

    def test_dataset_covers_difficult_search_dimensions(self):
        tags = {tag for case in self.cases for tag in case["tags"]}

        self.assertTrue(
            {
                "alias",
                "ambiguous",
                "evidence-text",
                "indirect-description",
                "paraphrase",
                "should-abstain",
                "typo",
            }.issubset(tags)
        )

    def test_duplicate_queries_are_rejected(self):
        duplicate = dict(self.cases[0])
        duplicate["id"] = "duplicate-case"

        with self.assertRaisesRegex(ValueError, "duplicate query"):
            validate_cases([self.cases[0], duplicate])

    def test_query_cases_require_an_intent(self):
        invalid = {
            "id": "missing-intent",
            "split": "development",
            "query": "Who owns Frontend?",
            "expected": {"operation": "query", "entities": []},
            "tags": ["invalid"],
        }

        with self.assertRaisesRegex(ValueError, "require an expected intent"):
            validate_cases([invalid])


if __name__ == "__main__":
    unittest.main()
