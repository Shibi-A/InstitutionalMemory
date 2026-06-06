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

Derived contribution relationships contain:

- `confidence`: `1 - exp(-evidence_weight)`
- `strength`: the person's share of evidence for that project and contribution type
- `evidence_count`
- `evidence_weight`
- `last_calculated_at`
- `supporting_evidence_count`
- `contradicting_evidence_count`
- `contradicting_evidence_weight`

Contradictory evidence lowers confidence and effective strength without deleting
the historical supporting evidence or its relationship summary.

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
