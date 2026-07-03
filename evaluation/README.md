# Semantic Search Evaluation Dataset

`search_cases.jsonl` is the fixed benchmark for routing, intent classification,
entity resolution, and abstention. Each line is an independent JSON object.

Required fields:

- `id`: stable unique case identifier
- `split`: `development`, `test`, or `regression`
- `query`: user input
- `expected.operation`: `query`, `update`, `feedback`, `ingestion`, or `abstain`
- `expected.intent`: expected query/update intent when applicable
- `expected.entities`: ordered expected graph entities
- `tags`: dimensions used for grouped reporting

The development split is used while tuning retrieval. The test split should
remain untouched during tuning. Regression cases record previously observed
failures and must not regress.

Some benchmark cases intentionally fail the current system. Dataset validation
checks structure and labels, not current retrieval performance.

Compare cosine-only entity retrieval with BM25-plus-cosine rank fusion:

```sh
.venv/bin/python -m evaluation.run_entity_retrieval_eval
```

The first benchmark evaluates cases with exactly one expected entity. Intent,
multi-entity extraction, and abstention are measured separately.
