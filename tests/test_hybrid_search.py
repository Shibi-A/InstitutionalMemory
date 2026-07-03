import unittest

from scoring.hybrid_search import (
    BM25Retriever,
    RankedDocument,
    SearchDocument,
    reciprocal_rank_fusion,
)


class HybridSearchTests(unittest.TestCase):
    def test_bm25_rewards_rare_matching_terms(self):
        retriever = BM25Retriever(
            [
                SearchDocument("auth", "authentication login latency"),
                SearchDocument("notify", "notification delivery latency"),
            ]
        )

        ranking = retriever.score("authentication latency")

        self.assertEqual(ranking[0].key, "auth")

    def test_bm25_omits_documents_without_matching_terms(self):
        retriever = BM25Retriever([SearchDocument("auth", "authentication login")])

        self.assertEqual(retriever.score("compiler"), [])

    def test_reciprocal_rank_fusion_combines_rankings(self):
        fused = reciprocal_rank_fusion(
            [
                [RankedDocument("auth", 0.9), RankedDocument("billing", 0.8)],
                [RankedDocument("auth", 4.0)],
            ]
        )

        self.assertEqual(fused[0].key, "auth")


if __name__ == "__main__":
    unittest.main()
