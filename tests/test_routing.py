import unittest

from retrieval.graph_question import classify_operation
from retrieval.graph_update import parse_project_assignment


class GraphRoutingTests(unittest.TestCase):
    def test_contribution_statement_is_update(self):
        self.assertEqual(classify_operation("Sam built the compiler"), ("update", 1.0))
        self.assertEqual(
            parse_project_assignment("Sam built the compiler"),
            ("Sam", "IMPLEMENTED", "compiler"),
        )

    def test_contribution_question_is_query(self):
        self.assertEqual(classify_operation("Who built the compiler?"), ("query", 1.0))

    def test_question_prefix_wins_over_update_verb(self):
        self.assertEqual(
            classify_operation("Does Sam work on Backend?"),
            ("query", 1.0),
        )

    def test_declarative_statement_is_update(self):
        self.assertEqual(
            classify_operation("Sam is a Backend Engineer"),
            ("update", 1.0),
        )

    def test_information_request_without_question_mark_is_query(self):
        self.assertEqual(
            classify_operation("Tell me who owns Frontend"),
            ("query", 1.0),
        )

    def test_contribution_aliases_are_implemented(self):
        for verb in ("built", "created", "developed", "implemented"):
            with self.subTest(verb=verb):
                parsed = parse_project_assignment(f"Sam {verb} Backend")
                self.assertEqual(parsed, ("Sam", "IMPLEMENTED", "Backend"))

    def test_batch_ingest_statement_is_update_shaped(self):
        self.assertEqual(
            classify_operation("ingest everything in sample documents"),
            ("update", 1.0),
        )

    def test_feedback_statement_is_update_shaped(self):
        self.assertEqual(
            classify_operation("no Alice built Backend not Bob"),
            ("update", 1.0),
        )


if __name__ == "__main__":
    unittest.main()
