import unittest

from evidence.service import (
    calculate_adjusted_confidence,
    calculate_confidence,
    calculate_effective_weight,
    calculate_decay_multiplier,
    calculate_decayed_weight,
    calculate_strength,
)


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

    def test_contradiction_lowers_confidence_and_effective_weight(self):
        supported = calculate_adjusted_confidence(2.0, 0.0)
        contradicted = calculate_adjusted_confidence(2.0, 1.0)

        self.assertLess(contradicted, supported)
        self.assertEqual(calculate_effective_weight(2.0, 1.0), 1.0)

    def test_evidence_loses_half_its_weight_after_one_half_life(self):
        self.assertAlmostEqual(calculate_decay_multiplier(365, 365), 0.5)
        self.assertAlmostEqual(calculate_decayed_weight(1.0, 365, 365), 0.5)

    def test_recent_evidence_outweighs_old_evidence(self):
        recent = calculate_decayed_weight(1.0, 30, 365)
        old = calculate_decayed_weight(1.0, 1095, 365)

        self.assertGreater(recent, old)


if __name__ == "__main__":
    unittest.main()
