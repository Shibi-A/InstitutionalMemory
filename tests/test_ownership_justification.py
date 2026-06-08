import unittest

from retrieval.graph_query import rank_ownership_candidates


class OwnershipJustificationTests(unittest.TestCase):
    def test_design_can_infer_owner_over_implementation(self):
        candidates = rank_ownership_candidates(
            [
                {
                    "person": "Alice",
                    "contribution": "DESIGNS",
                    "confidence": 0.8,
                    "strength": 1.0,
                    "statements": ["Alice designed React for Frontend."],
                },
                {
                    "person": "Bob",
                    "contribution": "IMPLEMENTED",
                    "confidence": 0.8,
                    "strength": 1.0,
                    "statements": [],
                },
            ]
        )

        self.assertEqual(candidates[0].person, "Alice")
        self.assertFalse(candidates[0].direct_owner)
        self.assertIn("Alice designed React for Frontend.", candidates[0].criteria[1])

    def test_direct_owner_wins_over_inferred_candidates(self):
        candidates = rank_ownership_candidates(
            [
                {
                    "person": "Alice",
                    "contribution": "DESIGNS",
                    "confidence": 1.0,
                    "strength": 1.0,
                    "statements": [],
                },
                {
                    "person": "Bob",
                    "contribution": "OWNED",
                    "confidence": 0.5,
                    "strength": 1.0,
                    "statements": [],
                },
            ]
        )

        self.assertEqual([candidate.person for candidate in candidates], ["Bob"])
        self.assertTrue(candidates[0].direct_owner)


if __name__ == "__main__":
    unittest.main()
