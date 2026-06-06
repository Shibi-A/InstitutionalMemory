import unittest

from ingestion.document_ingest import infer_evidence, parse_document


class DocumentIngestTests(unittest.TestCase):
    def test_owner_subject_creates_inferred_design_evidence(self):
        document = parse_document(
            "Title: Compiler Notes\nOwner: Bob\nSubject: Compilers\n\nNotes."
        )

        evidence = infer_evidence(document)

        self.assertEqual(evidence[0].person, "Bob")
        self.assertEqual(evidence[0].project, "Compilers")
        self.assertEqual(evidence[0].contribution_type, "DESIGNS")
        self.assertEqual(evidence[0].level, "inferred")

    def test_explicit_statement_creates_explicit_evidence(self):
        document = parse_document(
            "Owner: Bob\nSubject: Compilers\n\nAlice implemented Parser."
        )

        evidence = infer_evidence(document)

        self.assertEqual(evidence[1].person, "Alice")
        self.assertEqual(evidence[1].project, "Parser")
        self.assertEqual(evidence[1].contribution_type, "IMPLEMENTED")
        self.assertEqual(evidence[1].level, "explicit")

    def test_lowercase_work_object_maps_to_document_subject(self):
        document = parse_document(
            "Owner: Alice Kim\nSubject: Authentication Service\n\n"
            "Bob Chen implemented the token validation module."
        )

        evidence = infer_evidence(document)

        self.assertEqual(evidence[1].person, "Bob Chen")
        self.assertEqual(evidence[1].project, "Authentication Service")
        self.assertEqual(evidence[1].contribution_type, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
