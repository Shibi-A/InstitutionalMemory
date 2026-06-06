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

Derived contribution relationships contain:

- `confidence`: `1 - exp(-evidence_weight)`
- `strength`: the person's share of evidence for that project and contribution type
- `evidence_count`
- `evidence_weight`
- `last_calculated_at`

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
