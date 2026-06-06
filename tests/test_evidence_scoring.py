import unittest

from evidence.service import calculate_confidence, calculate_strength


class EvidenceScoringTests(unittest.TestCase):
    def test_confidence_has_diminishing_returns(self):
        first = calculate_confidence(1.0)
        second = calculate_confidence(2.0)

        self.assertGreater(second, first)
        self.assertLess(second, 1.0)
        self.assertLess(second - first, first)

    def test_strength_is_share_of_project_type_evidence(self):
        self.assertAlmostEqual(calculate_strength(3.0, 4.0), 0.75)
        self.assertAlmostEqual(calculate_strength(1.0, 4.0), 0.25)


if __name__ == "__main__":
    unittest.main()
