# Evidence-Backed Contributions

Contribution relationships such as `DESIGNS`, `IMPLEMENTED`, and `OWNED` are
derived summaries. `Evidence` nodes are the source of truth.

```text
(Person)-[:HAS_EVIDENCE]->(Evidence)-[:ABOUT]->(Project)
```

Evidence properties include:

- `level`: `explicit`, `inferred`, or `aggregated`
- `weight`: contribution to confidence and strength
- `source`: where the evidence came from
- `source_document_id`: document provenance when applicable
- `inference_rule`: rule used for inferred evidence
- `contribution_type`: relationship being supported
- `statement`: human-readable supporting statement
- `polarity`: `1` for supporting evidence or `-1` for contradictory evidence
- `observed_at`: when the evidence was produced or observed

Derived contribution relationships contain:

- `confidence`: confidence calculated from decayed supporting and contradictory weight
- `strength`: the person's share of evidence for that project and contribution type
- `evidence_count`
- `evidence_weight`: raw supporting weight
- `decayed_evidence_weight`: supporting weight after time decay
- `last_calculated_at`
- `supporting_evidence_count`
- `contradicting_evidence_count`
- `contradicting_evidence_weight`: raw contradictory weight
- `decayed_contradicting_evidence_weight`: contradictory weight after time decay

Contradictory evidence lowers confidence and effective strength without deleting
the historical supporting evidence or its relationship summary.

Evidence also decays exponentially over time:

```text
decayed weight = base weight * 0.5 ^ (age days / half-life days)
```

The default half-life is `365` days and can be configured with
`EVIDENCE_HALF_LIFE_DAYS`. A document can specify `Date: YYYY-MM-DD`; otherwise
its evidence begins aging from ingestion time.

Refresh all derived relationship scores as evidence ages:

```sh
.venv/bin/python -m evidence.recalculate
```

This also initializes `observed_at` from `created_at` for evidence created
before time decay was introduced.

## GitHub Repository Ingestion

Recent public-repository commits can be ingested from the general prompt:

```text
ingest https://github.com/openai/openai-python
```

The importer creates this provenance structure:

```text
(Person)-[:AUTHORED]->(Commit)-[:BELONGS_TO]->(Repository)
(Commit)-[:PROVIDES]->(Evidence)-[:ABOUT]->(Project)
(Commit)-[:TOUCHES]->(Project)
```

Commit-backed evidence supports `IMPLEMENTED` relationships. It is deliberately
weak, capped at `0.30` per commit/component, and subject to time decay. Merge
commits, bots, generated directories, dependency locks, and vendor content are
ignored. Repositories are split into repository-scoped projects based on paths,
and already-ingested commits are skipped on later runs.

GitHub ingestion also infers technology skills from changed file extensions,
dependency manifests, repository paths, and added patch lines:

```text
(Repository)-[:USES]->(Skill)
(Project)-[:USES]->(Skill)
(Commit)-[:USES]->(Skill)
(Person)-[:HAS_SKILL]->(Skill)
```

`HAS_SKILL` is a derived, evidence-backed relationship. Repeated recent usage
increases confidence and strength; older usage decays. Removing a technology
from a patch does not create new skill evidence. Rerunning ingestion backfills
skills for commits ingested before skill inference was introduced.

## User Feedback

Corrections can be entered directly in `retrieval/graph_question.py`:

```text
no Alice built Compilation Service not Bob
```

After confirmation, this creates supporting `IMPLEMENTED` evidence for Alice
and contradictory `IMPLEMENTED` evidence for Bob. Both evidence records remain
available when asking why the system believes a relationship exists.

## Document Ingestion

Run:

```sh
.venv/bin/python -m ingestion.document_ingest
```

Paste a structured document:

```text
Title: Compiler Architecture Notes
Owner: Bob
Subject: Compilers
Date: 2025-06-08

Alice implemented Parser.
END
```

The owner/subject pair creates inferred `DESIGNS` evidence. Explicit statements
in the content create explicit evidence.

Remove a document and its evidence:

```sh
.venv/bin/python -m ingestion.document_remove <document-id>
```

Batch ingest every new single-document `.txt` file in `sample_docs/`:

```sh
.venv/bin/python -m ingestion.batch_ingest sample_docs
```

The same batch can be started from `retrieval/graph_question.py` by entering:

```text
ingest everything in sample documents
```

## Ownership Justification

Ownership questions return a conclusion and the criteria used to reach it:

```text
Who owns Frontend?
```

Direct `OWNED` evidence takes precedence. When no direct owner exists, the
system ranks candidates using relationship confidence, relative contribution
strength, and these initial ownership-signal weights:

- `OWNED`: `1.00`
- `DESIGNS`: `0.75`
- `IMPLEMENTED`: `0.55`

The displayed ownership likelihood is relative among candidates considered,
not an absolute probability. Supporting evidence statements are included when
available, and alternative candidates are shown for transparency.
