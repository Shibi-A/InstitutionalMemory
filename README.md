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

## Ask Questions And Update The Graph

```sh
.venv/bin/python retrieval/graph_question.py
```

Examples:

```text
Who knows about Frontend?
Why do we think Bob implemented Frontend?
Sam built the compiler
Remove Sam
quit
```

## Document Ingestion

```sh
.venv/bin/python -m ingestion.document_ingest
```

Example input:

```text
Title: Compiler Architecture Notes
Owner: Bob
Subject: Compilers

Alice implemented Parser.
END
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```
