import unittest
from pathlib import Path

from ingestion.batch_ingest import load_documents


class BatchIngestTests(unittest.TestCase):
    def test_sample_documents_are_independent_valid_files(self):
        documents, errors = load_documents(Path("sample_docs"))

        self.assertEqual(errors, [])
        self.assertEqual(len(documents), 11)
        self.assertEqual(len({document.document_id for _, document in documents}), 11)


if __name__ == "__main__":
    unittest.main()
