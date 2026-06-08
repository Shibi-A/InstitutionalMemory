import unittest

from ingestion.github_client import GitHubRepository
from ingestion.github_repository_ingest import (
    commit_author,
    commit_evidence_weight,
    component_for_file,
    is_ignored_commit,
)
from retrieval.graph_question import extract_github_repository


class GitHubRepositoryIngestTests(unittest.TestCase):
    def setUp(self):
        self.repository = GitHubRepository("openai", "openai-python")

    def test_github_url_is_extracted_from_ingest_command(self):
        repository = extract_github_repository(
            "ingest https://github.com/openai/openai-python.git"
        )

        self.assertEqual(repository, "openai/openai-python")

    def test_owner_repository_identifier_is_extracted(self):
        self.assertEqual(
            extract_github_repository("ingest openai/openai-python"),
            "openai/openai-python",
        )

    def test_source_container_maps_to_named_component(self):
        component = component_for_file(
            self.repository,
            "src/openai/resources/chat/completions.py",
        )

        self.assertEqual(component, "openai/openai-python: Openai")

    def test_top_level_directory_maps_to_component(self):
        component = component_for_file(self.repository, "ingestion/document.py")

        self.assertEqual(component, "openai/openai-python: Ingestion")

    def test_generated_and_lock_files_are_ignored(self):
        self.assertIsNone(component_for_file(self.repository, "package-lock.json"))
        self.assertIsNone(component_for_file(self.repository, "generated/client.py"))

    def test_commit_weight_is_capped(self):
        self.assertLess(commit_evidence_weight(1), commit_evidence_weight(100))
        self.assertEqual(commit_evidence_weight(1_000_000), 0.30)

    def test_github_login_is_preferred_as_author(self):
        commit = {
            "author": {"login": "alice"},
            "commit": {"author": {"name": "Alice Smith"}},
        }

        self.assertEqual(commit_author(commit), "alice")

    def test_bots_and_merge_commits_are_ignored(self):
        bot = {"author": {"login": "dependabot[bot]"}, "parents": [{}]}
        merge = {"author": {"login": "alice"}, "parents": [{}, {}]}

        self.assertTrue(is_ignored_commit(bot))
        self.assertTrue(is_ignored_commit(merge))


if __name__ == "__main__":
    unittest.main()
