import unittest

from retrieval.graph_query import classify_intent


class GraphQueryIntentTests(unittest.TestCase):
    def test_knows_about_project_maps_to_contributors(self):
        intent, confidence = classify_intent("Who knows about a compiler?")

        self.assertEqual(intent.name, "project_contributors")
        self.assertGreater(confidence, 0.7)

    def test_why_question_maps_to_relationship_evidence(self):
        intent, confidence = classify_intent(
            "Why do we think Bob implemented Frontend?"
        )

        self.assertEqual(intent.name, "relationship_evidence")
        self.assertEqual(confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
