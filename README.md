# Institutional Memory

An experimental organizational knowledge graph built with Neo4j and Chroma.
It supports natural-language graph queries, controlled graph updates,
evidence-backed contribution scoring, and structured document ingestion.

## Features

- Route question-shaped input to graph retrieval and statements to updates.
- Match query and update intents locally with Chroma embeddings.
- Track `Person`, `Project`, `Role`, `Document`, and `Evidence` nodes in Neo4j.
- Derive contribution confidence and relative strength from supporting evidence.
- Infer contribution evidence from document ownership and subject metadata.
- Preserve document provenance so inferred evidence can be explained or removed.

## Setup

Neo4j should be running locally at `bolt://localhost:7687`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m evidence.setup
```

Connection defaults can be overridden with:

```sh
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
```

Public GitHub repository ingestion can run without authentication. Optionally
provide a token to increase GitHub API rate limits:

```sh
export GITHUB_TOKEN="github_pat_..."
```

Never commit the token to the repository.

## Ask Questions And Update The Graph

```sh
.venv/bin/python retrieval/graph_question.py
```

Examples:

```text
Who knows about Frontend?
Who owns Frontend?
Why do we think Bob implemented Frontend?
Sam built the compiler
Remove Sam
no Alice built Compilation Service not Bob
ingest https://github.com/openai/openai-python
quit
```

GitHub repository ingestion analyzes the most recent 25 non-merge commits by
default. Configure the limit when needed:

```sh
export GITHUB_COMMIT_LIMIT=100
.venv/bin/python -m ingestion.github_repository_ingest openai/openai-python
```

Each commit creates weak, timestamped `IMPLEMENTED` evidence for the repository
components it changed. Re-running ingestion skips commits already stored in the
graph.

## Document Ingestion

```sh
.venv/bin/python -m ingestion.document_ingest
```

Ingest one document file:

```sh
.venv/bin/python -m ingestion.document_ingest \
  sample_docs/authentication_service_migration.txt
```

Ingest every new document in `sample_docs/`:

```sh
.venv/bin/python -m ingestion.batch_ingest sample_docs
```

Example input:

```text
Title: Compiler Architecture Notes
Owner: Bob
Subject: Compilers
Date: 2025-06-08

Alice implemented Parser.
END
```

Refresh time-decayed relationship scores:

```sh
.venv/bin/python -m evidence.recalculate
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```
