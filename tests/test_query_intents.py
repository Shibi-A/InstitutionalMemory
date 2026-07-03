import unittest

from retrieval.graph_query import classify_intent, extract_entity_hint


class GraphQueryIntentTests(unittest.TestCase):
    def test_who_owns_project_maps_to_owner_justification(self):
        intent, confidence = classify_intent("Who owns Frontend?")

        self.assertEqual(intent.name, "project_owner")
        self.assertEqual(confidence, 1.0)

    def test_owner_question_extracts_project_hint(self):
        self.assertEqual(extract_entity_hint("Who owns Frotend?", "Project"), "Frotend")

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

    def test_skill_question_maps_to_skill_experts(self):
        intent, confidence = classify_intent("Who has experience with Neo4j?")

        self.assertEqual(intent.name, "skill_experts")
        self.assertEqual(confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
