"""Ingest recent public GitHub repository activity as contribution evidence."""

import math
import os
import re
import sys
import uuid
from collections import defaultdict
from pathlib import PurePosixPath

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evidence.service import add_contribution_evidence, recalculate_relationship_scores
from ingestion.document_ingest import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from ingestion.github_client import (
    GitHubAPIError,
    GitHubClient,
    GitHubRepository,
    parse_github_repository,
)


DEFAULT_COMMIT_LIMIT = int(os.getenv("GITHUB_COMMIT_LIMIT", "25"))
IGNORED_FILE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}
IGNORED_PATH_PARTS = {
    ".github",
    "dist",
    "generated",
    "node_modules",
    "vendor",
}
CONTAINER_DIRECTORIES = {"apps", "lib", "packages", "services", "src"}


def humanize_component(value: str) -> str:
    words = re.sub(r"[-_.]+", " ", value).strip()
    return words.title() if words else "Repository Root"


def component_for_file(repository: GitHubRepository, filename: str):
    path = PurePosixPath(filename)
    if path.name.lower() in IGNORED_FILE_NAMES:
        return None
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & IGNORED_PATH_PARTS:
        return None

    parts = path.parts
    if len(parts) == 1:
        component = "Repository Root"
    elif parts[0].lower() in CONTAINER_DIRECTORIES and len(parts) > 2:
        component = humanize_component(parts[1])
    else:
        component = humanize_component(parts[0])
    return f"{repository.full_name}: {component}"


def commit_evidence_weight(changes: int) -> float:
    return min(0.30, 0.05 + 0.05 * math.log2(max(1, changes)))


def commit_author(commit: dict) -> str:
    github_author = commit.get("author") or {}
    if github_author.get("login"):
        return github_author["login"]
    raw_author = commit.get("commit", {}).get("author", {})
    return raw_author.get("name") or raw_author.get("email") or "Unknown Contributor"


def is_ignored_commit(commit: dict) -> bool:
    author = commit_author(commit).lower()
    return author.endswith("[bot]") or len(commit.get("parents") or []) > 1


def repository_commit_exists(driver, repository: GitHubRepository, sha: str) -> bool:
    records, _, _ = driver.execute_query(
        """
        MATCH (commit:Commit {repository: $repository, sha: $sha})
        RETURN count(commit) AS count
        """,
        repository=repository.full_name,
        sha=sha,
        database_="neo4j",
    )
    return records[0]["count"] > 0


def ingest_commit(driver, repository: GitHubRepository, commit: dict) -> set[str]:
    sha = commit["sha"]
    author = commit_author(commit)
    commit_data = commit.get("commit", {})
    message = (commit_data.get("message") or "").splitlines()[0]
    observed_at = commit_data.get("author", {}).get("date")
    component_changes = defaultdict(int)
    for file_data in commit.get("files") or []:
        component = component_for_file(repository, file_data.get("filename", ""))
        if component:
            component_changes[component] += file_data.get("changes") or 0

    driver.execute_query(
        """
        MERGE (repository:Repository {full_name: $repository})
        SET repository.url = $repository_url
        MERGE (commit:Commit {repository: $repository, sha: $sha})
        SET commit.message = $message,
            commit.url = $commit_url,
            commit.observed_at = datetime($observed_at)
        MERGE (person:Person {name: $author})
        MERGE (person)-[:AUTHORED]->(commit)
        MERGE (commit)-[:BELONGS_TO]->(repository)
        """,
        repository=repository.full_name,
        repository_url=f"https://github.com/{repository.full_name}",
        sha=sha,
        message=message,
        commit_url=commit.get("html_url"),
        observed_at=observed_at,
        author=author,
        database_="neo4j",
    )

    for component, changes in component_changes.items():
        evidence_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"github_commit:{repository.full_name}:{sha}:{component}",
            )
        )
        add_contribution_evidence(
            driver,
            person=author,
            project=component,
            contribution_type="IMPLEMENTED",
            level="aggregated",
            weight=commit_evidence_weight(changes),
            source="github_commit",
            source_document_id=f"github:{repository.full_name}:{sha}",
            inference_rule="commit_touched_component",
            observed_at=observed_at,
            statement=f'{author} changed {component} in commit "{message}" ({sha[:7]}).',
            evidence_id=evidence_id,
            recalculate=False,
        )
        driver.execute_query(
            """
            MATCH (commit:Commit {repository: $repository, sha: $sha}),
                  (evidence:Evidence {id: $evidence_id}),
                  (project:Project {name: $component})
            MERGE (commit)-[:PROVIDES]->(evidence)
            MERGE (commit)-[:TOUCHES]->(project)
            """,
            repository=repository.full_name,
            sha=sha,
            evidence_id=evidence_id,
            component=component,
            database_="neo4j",
        )
    return set(component_changes)


def ingest_github_repository(
    repository_value: str,
    *,
    commit_limit: int = DEFAULT_COMMIT_LIMIT,
    client=None,
) -> int:
    try:
        repository = parse_github_repository(repository_value)
        client = client or GitHubClient()
        metadata = client.get_repository(repository)
        page_size = min(max(1, commit_limit), 100)
        commits = client.list_commits(repository, per_page=page_size)[:commit_limit]
        authentication = "authenticated" if client.authenticated else "unauthenticated"
        print(
            f"Repository: {metadata.get('full_name', repository.full_name)} "
            f"({authentication} GitHub API)"
        )
        print(f"Recent commits available for ingestion: {len(commits)}")
        if input("Ingest recent repository activity? [y/N]: ").strip().lower() != "y":
            print("Repository ingestion cancelled.")
            return 0

        with GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        ) as driver:
            ingested = 0
            skipped = 0
            score_groups = set()
            for summary in commits:
                sha = summary["sha"]
                if repository_commit_exists(driver, repository, sha):
                    skipped += 1
                    continue
                commit = client.get_commit(repository, sha)
                if is_ignored_commit(commit):
                    skipped += 1
                    continue
                components = ingest_commit(driver, repository, commit)
                score_groups.update((component, "IMPLEMENTED") for component in components)
                ingested += 1
            for project, contribution_type in score_groups:
                recalculate_relationship_scores(driver, project, contribution_type)
    except (GitHubAPIError, Neo4jError, ServiceUnavailable, ValueError) as error:
        print(f"Could not ingest GitHub repository: {error}", file=sys.stderr)
        return 1

    print(
        f"Repository ingestion completed: commits ingested={ingested}, "
        f"commits skipped={skipped}, components updated={len(score_groups)}."
    )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m ingestion.github_repository_ingest <github-repository>")
        return 1
    return ingest_github_repository(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
