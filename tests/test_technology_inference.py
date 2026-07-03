import unittest

from ingestion.technology_inference import infer_file_skills


class TechnologyInferenceTests(unittest.TestCase):
    def test_file_extension_infers_language(self):
        self.assertEqual(
            infer_file_skills({"filename": "service/main.py"}),
            {"Python"},
        )

    def test_typescript_react_file_infers_both_skills(self):
        self.assertEqual(
            infer_file_skills({"filename": "frontend/App.tsx"}),
            {"React", "TypeScript"},
        )

    def test_added_dependency_usage_infers_technology(self):
        skills = infer_file_skills(
            {
                "filename": "graph/service.py",
                "patch": "@@ -1 +1 @@\n+from neo4j import GraphDatabase",
            }
        )

        self.assertEqual(skills, {"Neo4j", "Python"})

    def test_removed_dependency_usage_does_not_infer_technology(self):
        skills = infer_file_skills(
            {
                "filename": "graph/service.py",
                "patch": "@@ -1 +1 @@\n-from neo4j import GraphDatabase\n+pass",
            }
        )

        self.assertEqual(skills, {"Python"})

    def test_manifest_infers_runtime(self):
        self.assertEqual(
            infer_file_skills({"filename": "package.json"}),
            {"JavaScript", "Node.js"},
        )


if __name__ == "__main__":
    unittest.main()
