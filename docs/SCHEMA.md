# Storage contract: schema version 1

InferencePilot v0.1.0 freezes SQLite schema version **1**. The exact DDL is recorded
in [schema-v1.sql](schema-v1.sql), matching `store.SCHEMA` and the master specification.
SHA-256 of its UTF-8 bytes:

```text
26164661686f9a8dfaecb60a02d96e801f2ff6d0cd6a0d024856736b4f879a59
```

The snapshot/hash test detects accidental changes to this released contract.
`schema_meta.version` remains `1`; it is independent of the package's `0.1.0`
version. Opening an incompatible schema version fails explicitly. No destructive
or implicit migration is performed. A future incompatible change requires a new
schema version and explicit compatibility/migration design; retain the v1 snapshot.

Connections enable foreign keys and WAL. Rep rows and logical checkpoints commit
atomically. Quality measurements and reusable source pointers also commit together.
Detailed arrays and logs remain outside SQLite, with paths/summaries in the store.
Backups use SQLite's backup API so committed WAL contents are included consistently.

Re-analysis replaces regression rows, while recommendations retain execution
history. `schema_meta` also stores plans' execution metadata and provenance; adding
an application metadata key does not change the frozen table/index DDL. Report JSON
has its own `schema_version=1`; it must not be confused with a future package bump.
