"""Minimal GitHub API client for public repository ingestion."""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")


class GitHubAPIError(RuntimeError):
    """Raised when GitHub cannot fulfill an API request."""


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_github_repository(value: str) -> GitHubRepository:
    match = re.fullmatch(
        r"(?:https?://github\.com/)?"
        r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        value.strip(),
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            "Expected a GitHub repository URL or owner/repository identifier."
        )
    return GitHubRepository(match.group("owner"), match.group("name"))


def build_github_headers(token: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "InstitutionalMemory",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resolved_token = token if token is not None else os.getenv("GITHUB_TOKEN")
    if resolved_token:
        headers["Authorization"] = f"Bearer {resolved_token}"
    return headers


class GitHubClient:
    def __init__(
        self,
        token: Optional[str] = None,
        api_url: str = GITHUB_API_URL,
    ) -> None:
        self.headers = build_github_headers(token)
        self.api_url = api_url.rstrip("/")

    @property
    def authenticated(self) -> bool:
        return "Authorization" in self.headers

    def get(self, path: str, parameters: Optional[dict] = None):
        query = f"?{urlencode(parameters)}" if parameters else ""
        request = Request(
            f"{self.api_url}/{path.lstrip('/')}{query}",
            headers=self.headers,
        )
        try:
            with urlopen(request) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 403:
                raise GitHubAPIError(
                    "GitHub rejected the request. Configure GITHUB_TOKEN if the "
                    "public API rate limit was exceeded."
                ) from error
            if error.code == 404:
                raise GitHubAPIError(
                    "GitHub repository or resource was not found."
                ) from error
            raise GitHubAPIError(f"GitHub API request failed: HTTP {error.code}.") from error
        except URLError as error:
            raise GitHubAPIError(f"Could not connect to GitHub: {error.reason}") from error

    def get_repository(self, repository: GitHubRepository):
        return self.get(f"/repos/{repository.full_name}")

    def list_commits(
        self,
        repository: GitHubRepository,
        *,
        page: int = 1,
        per_page: int = 100,
    ):
        return self.get(
            f"/repos/{repository.full_name}/commits",
            {"page": page, "per_page": per_page},
        )

    def get_commit(self, repository: GitHubRepository, sha: str):
        return self.get(f"/repos/{repository.full_name}/commits/{sha}")
