"""Infer technology skills from repository file metadata and patches."""

from pathlib import PurePosixPath


EXTENSION_SKILLS = {
    ".c": {"C"},
    ".cpp": {"C++"},
    ".cs": {"C#"},
    ".css": {"CSS"},
    ".cypher": {"Cypher"},
    ".go": {"Go"},
    ".html": {"HTML"},
    ".java": {"Java"},
    ".js": {"JavaScript", "Node.js"},
    ".jsx": {"JavaScript", "React"},
    ".kt": {"Kotlin"},
    ".php": {"PHP"},
    ".py": {"Python"},
    ".rb": {"Ruby"},
    ".rs": {"Rust"},
    ".sql": {"SQL"},
    ".swift": {"Swift"},
    ".tf": {"Terraform"},
    ".ts": {"TypeScript", "Node.js"},
    ".tsx": {"TypeScript", "React"},
}
FILENAME_SKILLS = {
    "cargo.toml": {"Rust"},
    "dockerfile": {"Docker"},
    "go.mod": {"Go"},
    "package.json": {"JavaScript", "Node.js"},
    "pom.xml": {"Java", "Maven"},
    "pyproject.toml": {"Python"},
    "requirements.txt": {"Python"},
}
CONTENT_SKILLS = {
    "chromadb": "Chroma",
    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "kubernetes": "Kubernetes",
    "neo4j": "Neo4j",
    "postgresql": "PostgreSQL",
    "react": "React",
    "terraform": "Terraform",
}


def infer_file_skills(file_data: dict) -> set[str]:
    filename = file_data.get("filename", "")
    path = PurePosixPath(filename)
    skills = set(EXTENSION_SKILLS.get(path.suffix.lower(), set()))
    skills.update(FILENAME_SKILLS.get(path.name.lower(), set()))

    added_lines = "\n".join(
        line[1:]
        for line in (file_data.get("patch") or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    searchable = f"{filename}\n{added_lines}".casefold()
    for keyword, skill in CONTENT_SKILLS.items():
        if keyword in searchable:
            skills.add(skill)
    return skills
