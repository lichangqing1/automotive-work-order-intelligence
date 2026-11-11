# Dataset-version semantics

`DatasetVersion.dataset_version_id` is the authoritative persistent identity.
Public APIs also accept a human `version` label when it resolves to exactly one
record. Unknown labels fail with no latest-version fallback, and ambiguous
labels must be replaced with the canonical ID.

## Persisted scopes

- `work_order_snapshots` is the immutable clean/curated record set. Its
  `(dataset_version_id, work_order_id)` constraint preserves repeated business
  IDs across versions while rejecting duplicates within one version.
- `ingestion_runs` records clean and quarantined counts for its exact dataset
  version. Source count is `ingested_rows + rejected_rows`.
- `work_orders`, `vehicles`, diagnostic events, and resolution history are
  mutable operational projections. They are used by the unversioned overview
  endpoint and must not be presented as historical dataset-version results.
- DQ runs store the canonical dataset-version ID. Their results remain
  historical after later ingestion.

Runtime reconciliation compares the source count and quarantine count with the
clean snapshot count for the same canonical version. Versioned KPI requests,
SQL validations, and PostgreSQL mart rows use that same snapshot scope. The
legacy `GET /api/v1/metrics/overview` response remains a current-state view;
`GET /api/v1/metrics/overview?dataset_version=<label-or-id>` returns immutable
version metrics plus explicit scope metadata.

The B1 isolation correction required no migration. B2 adds a versioned
full-source fingerprint and durable ingestion-attempt audit records while
retaining these scopes. Individual quarantined payloads are not persisted;
only their version-specific count is retained.
