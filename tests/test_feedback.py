import unittest

from retrieval.graph_feedback import parse_correction


class FeedbackTests(unittest.TestCase):
    def test_correction_extracts_positive_and_negative_facts(self):
        correction = parse_correction(
            "no Alice built the compilation service not Bob"
        )

        self.assertEqual(correction.correct_person, "Alice")
        self.assertEqual(correction.incorrect_person, "Bob")
        self.assertEqual(correction.project, "Compilation Service")
        self.assertEqual(correction.contribution_type, "IMPLEMENTED")

    def test_common_built_typo_is_supported(self):
        correction = parse_correction(
            "no Alice buit the compilation service not Bob"
        )

        self.assertEqual(correction.contribution_type, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
