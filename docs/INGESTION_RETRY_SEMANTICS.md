# Ingestion retry and failure-audit semantics

Ingestion idempotency is evaluated at the immutable dataset-version persistence
boundary. The surrounding platform runtime may subsequently create DQ evidence,
but it cannot create another successful `IngestionRun` for the same canonical
dataset version.

## Content identity

`source-json-multiset-v1` hashes all four complete source frames: work orders,
vehicles, OTA releases, and diagnostic events. Columns and serialized object
keys are sorted, source row order is ignored, duplicate rows remain represented,
and null/timestamp values are normalized. The fingerprint is calculated before
quarantine, so changed rejected rows cannot match merely because the curated
output is unchanged.

- A new version creates one `DatasetVersion`, one successful `IngestionRun`,
  and its immutable snapshots.
- An identical retry returns `ALREADY_INGESTED`, reuses the original run, and
  adds only an `IngestionAttempt` audit record.
- Different source content under the same version returns a sanitized
  `DatasetVersionConflict` and leaves the original version unchanged.
- Identical content under a different version is a legitimate new dataset.
- A legacy version without the new full-source fingerprint fails closed rather
  than guessing that a retry is identical.

## Transactions and auditing

The ingestion function owns its business transaction. Dataset identity,
reference projections, snapshots, diagnostics, and the successful ingestion
run commit atomically. On any exception the session is rolled back before it is
reused. A separate committed `IngestionAttempt` unit records request identity,
outcome, stage, sanitized error category, and row counts without source payloads
or raw database errors. This audit survives rollback of the business data.

Database uniqueness enforces one successful ingestion run per dataset version,
and snapshot uniqueness enforces one business ID per version. Concurrent
uniqueness races are re-read after rollback: identical content resolves as an
idempotent retry; different content resolves as a version conflict.

Migration `20261111_0003` adds nullable fingerprint fields for historical
compatibility, the attempt table, and the unique ingestion-run index. It does
not backfill or reinterpret historical hashes and does not modify snapshots.
