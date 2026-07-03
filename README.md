# Institutional Memory

Institutional Memory is an experimental organizational knowledge graph for
answering questions like:

```text
Who owns Authentication Service?
Who knows about Neo4j?
What does Alice Kim do?
Why do we think Bob Chen worked on Notification Platform?
```

The project combines Neo4j graph storage, local hybrid search with BM25 and
Chroma embeddings, evidence-backed scoring, document ingestion, and GitHub code
ingestion.

## What It Does

- Stores people, projects, roles, repositories, commits, documents, evidence,
  and inferred skills in Neo4j.
- Routes natural-language input as either a graph question, graph update,
  feedback correction, document ingestion, or GitHub ingestion command.
- Answers ownership, contributor, skill, role, supervisor, person-summary, and
  relationship-evidence questions.
- Ingests structured documents and infers contribution evidence from document
  owners, subjects, and explicit statements.
- Ingests public GitHub repositories and infers component contributions from
  recent commits.
- Infers technology skills from changed file extensions, dependency manifests,
  repository paths, and added patch lines.
- Keeps provenance through `Evidence`, `Document`, and `Commit` nodes so answers
  can explain why the graph believes something.
- Applies confidence scoring, contradiction handling, relative strength, and
  time decay so recent evidence matters more than stale evidence.
- Provides a semantic-search evaluation dataset for comparing cosine-only
  retrieval with hybrid BM25-plus-cosine retrieval.

## How It Works

The graph treats direct relationships such as `IMPLEMENTED`, `DESIGNS`,
`OWNED`, and `HAS_SKILL` as derived summaries. The source of truth is evidence.

```text
(Person)-[:HAS_EVIDENCE]->(Evidence)-[:ABOUT]->(Project)
(Person)-[:HAS_EVIDENCE]->(Evidence)-[:ABOUT]->(Skill)
```

For GitHub ingestion, commit provenance is also retained:

```text
(Person)-[:AUTHORED]->(Commit)-[:BELONGS_TO]->(Repository)
(Commit)-[:PROVIDES]->(Evidence)
(Commit)-[:TOUCHES]->(Project)
(Commit)-[:USES]->(Skill)
(Repository)-[:USES]->(Skill)
(Project)-[:USES]->(Skill)
```

Each evidence record has a base weight, source, statement, timestamp, and
inference rule. Derived relationships are recalculated from evidence and include
confidence, relative strength, evidence counts, and decayed evidence weight.

Time decay uses:

```text
decayed weight = base weight * 0.5 ^ (age days / half-life days)
```

The default half-life is 365 days and can be overridden with
`EVIDENCE_HALF_LIFE_DAYS`.

## Setup

Neo4j should be running locally at `bolt://localhost:7687`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m evidence.setup
```

Connection defaults:

```sh
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
```

Optional GitHub settings:

```sh
export GITHUB_TOKEN="github_pat_..."
export GITHUB_COMMIT_LIMIT=100
```

`GITHUB_TOKEN` is optional for public repositories, but it increases GitHub API
rate limits. Never commit tokens. `.env` is ignored.

## Main Interactive App

Run the general graph prompt:

```sh
.venv/bin/python retrieval/graph_question.py
```

Then enter questions, updates, feedback, or ingestion commands:

```text
Who owns Frontend?
Who knows about Authentication Service?
Who has experience with Neo4j?
What does Shibi-A do?
Why do we think Bob Chen worked on Notification Platform?

Sam built the compiler
Chris is a Backend Engineer
Shibi no longer works on Frontend
no Alice built Compilation Service not Bob

ingest everything in sample documents
ingest https://github.com/openai/openai-python

quit
```

Question-shaped input is routed to read-only retrieval. Statement-shaped input
is routed to controlled graph updates. Feedback beginning with `no ...` creates
corrective evidence without deleting the historical record.

## Document Ingestion

Ingest a document interactively:

```sh
.venv/bin/python -m ingestion.document_ingest
```

Ingest one file:

```sh
.venv/bin/python -m ingestion.document_ingest \
  sample_docs/authentication_service_migration.txt
```

Batch ingest every new `.txt` document in `sample_docs/`:

```sh
.venv/bin/python -m ingestion.batch_ingest sample_docs
```

The same batch can be started from the main prompt:

```text
ingest everything in sample documents
```

Document format:

```text
Title: Compiler Architecture Notes
Owner: Bob
Subject: Compilers
Date: 2025-06-08

Alice implemented Parser.
END
```

Document ingestion creates:

- a `Document` node
- `AUTHORED` and `ABOUT` provenance links
- inferred `DESIGNS` evidence from owner plus subject
- explicit contribution evidence from sentences like `Alice implemented Parser`

Remove a document and its evidence:

```sh
.venv/bin/python -m ingestion.document_remove <document-id>
```

## GitHub Code Ingestion

Ingest a public GitHub repository from the main prompt:

```text
ingest https://github.com/openai/openai-python
```

Or run the importer directly:

```sh
.venv/bin/python -m ingestion.github_repository_ingest openai/openai-python
```

By default, the importer analyzes the latest 25 commits. Configure more with:

```sh
export GITHUB_COMMIT_LIMIT=100
```

GitHub ingestion:

- creates `Repository` and `Commit` nodes
- maps changed paths into repository-scoped component `Project` nodes
- creates weak, timestamped `IMPLEMENTED` evidence for commit authors
- skips bots, merge commits, generated files, dependency locks, and vendor paths
- skips commits that have already been fully ingested
- backfills new inference types when the ingestion version changes
- infers skills such as `Python`, `React`, `Neo4j`, `Chroma`, `Node.js`, and
  `Docker` from file extensions, manifests, paths, and added patch lines

Skill evidence creates derived `HAS_SKILL` relationships, so users can ask:

```text
Who has experience with Python?
Who has experience with Neo4j?
What does Shibi-A do?
```

## Refresh Scores

Run this after changing decay settings or after time has passed and you want to
refresh derived scores:

```sh
.venv/bin/python -m evidence.recalculate
```

This refreshes project contribution scores and skill scores from current
evidence ages.

## Search And Evaluation

Semantic matching uses hybrid BM25-plus-Chroma retrieval. BM25 helps with exact
terms, names, acronyms, and technical words; Chroma embeddings help with looser
semantic matches. Rankings are fused with Reciprocal Rank Fusion.

The evaluation dataset lives in:

```text
evaluation/search_cases.jsonl
```

It includes development, test, and regression cases for routing, intent
classification, entity matching, aliases, typos, indirect descriptions, and
abstention.

Compare cosine-only entity retrieval against hybrid BM25-plus-cosine retrieval:

```sh
.venv/bin/python -m evaluation.run_entity_retrieval_eval
```

## Useful Commands

Set up Neo4j constraints:

```sh
.venv/bin/python -m evidence.setup
```

Backfill evidence from existing direct graph relationships:

```sh
.venv/bin/python -m evidence.backfill
```

Run the semantic-search demo:

```sh
.venv/bin/python -m scoring.semantic_search
```

Run tests:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

## Project Layout

```text
retrieval/   Natural-language graph questions and updates
ingestion/   Document, batch, GitHub, and technology ingestion
evidence/    Evidence creation, scoring, decay, refresh, and schema setup
scoring/     BM25, Chroma, and hybrid search utilities
evaluation/  Search evaluation dataset and benchmark runner
sample_docs/ Example structured documents
tests/       Unit tests
docs/        Design notes and evidence model details
```

## Current Limitations

- GitHub ingestion is intentionally heuristic. Commit activity supports
  contribution and skill evidence, but it is not proof of ownership by itself.
- Ownership is inferred from evidence weight, relationship type, relative
  strength, and recency. Direct `OWNED` evidence is stronger than repeated
  `IMPLEMENTED` evidence.
- Skill inference is based on file and patch signals; it can miss technologies
  that are only implied by architecture or runtime configuration.
- Similarity scores are ranking signals, not calibrated probabilities.
