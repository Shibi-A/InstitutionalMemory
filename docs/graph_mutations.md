# Graph Mutation Design

Natural-language writes should use a fixed set of mutation intents and
parameterized Cypher templates. Chroma can classify the intent and resolve
existing entities, but Python should control every write query.

The implementation is in `retrieval/graph_update.py`. General user input enters
through `retrieval/graph_question.py`, which delegates writes to this module.

## Initial Mutation Intents

| Intent | Example | Required values |
| --- | --- | --- |
| `add_person` | Chris joined the company | New person name |
| `remove_person` | Remove Shibi | Existing person |
| `assign_project` | Chris works on Frontend | Person, project, contribution |
| `unassign_project` | Shibi no longer works on Frontend | Person, project, contribution |
| `assign_role` | Chris is a Frontend Engineer | Person, role |
| `set_supervisor` | Chris works under Alice | Person, supervisor |

## Safety Rules

1. Resolve existing people, projects, and roles against Neo4j before writing.
2. Require an explicit contribution type: `DESIGNS`, `IMPLEMENTED`, or `OWNED`.
   "Works on" is ambiguous and should trigger a clarification.
3. Preview the intended change and require confirmation before execution.
4. Use parameterized, predefined Cypher only. Never generate arbitrary writes.
5. Use `MERGE` for additions so repeated commands do not create duplicates.
6. Report how many nodes and relationships changed.

## Relationship Consistency

`WORKS_UNDER` and `SUPERVISES` currently represent the same fact in opposite
directions. Supervisor mutations must update both relationships together:

```cypher
MATCH (person:Person), (supervisor:Person)
WHERE person.name = $person AND supervisor.name = $supervisor
MERGE (person)-[:WORKS_UNDER]->(supervisor)
MERGE (supervisor)-[:SUPERVISES]->(person)
```

Removing a person should use `DETACH DELETE`, but only after showing every
relationship that will also be deleted and receiving confirmation.
