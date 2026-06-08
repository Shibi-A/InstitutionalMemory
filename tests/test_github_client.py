import unittest
from unittest.mock import patch

from ingestion.github_client import (
    GitHubClient,
    build_github_headers,
    parse_github_repository,
)


class GitHubClientTests(unittest.TestCase):
    def test_repository_url_is_normalized(self):
        repository = parse_github_repository(
            "https://github.com/openai/openai-python.git"
        )

        self.assertEqual(repository.full_name, "openai/openai-python")

    def test_owner_repository_identifier_is_supported(self):
        repository = parse_github_repository("openai/openai-python")

        self.assertEqual(repository.owner, "openai")
        self.assertEqual(repository.name, "openai-python")

    def test_invalid_repository_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_github_repository("https://example.com/openai/openai-python")

    def test_token_is_optional(self):
        with patch.dict("os.environ", {}, clear=True):
            headers = build_github_headers()

        self.assertNotIn("Authorization", headers)

    def test_environment_token_is_used_when_available(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "secret"}):
            headers = build_github_headers()

        self.assertEqual(headers["Authorization"], "Bearer secret")

    def test_explicit_token_overrides_environment(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "environment-token"}):
            client = GitHubClient(token="explicit-token")

        self.assertTrue(client.authenticated)
        self.assertEqual(client.headers["Authorization"], "Bearer explicit-token")


if __name__ == "__main__":
    unittest.main()
