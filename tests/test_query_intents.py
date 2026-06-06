import unittest

from retrieval.graph_query import classify_intent


class GraphQueryIntentTests(unittest.TestCase):
    def test_what_does_person_do_maps_to_person_summary(self):
        intent, confidence = classify_intent("What does Alice do?")

        self.assertEqual(intent.name, "person_summary")
        self.assertEqual(confidence, 1.0)

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
