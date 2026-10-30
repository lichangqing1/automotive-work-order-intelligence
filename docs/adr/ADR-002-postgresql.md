# ADR-002: PostgreSQL as the platform store

## Context

SQLite supported the reproducible MVP but does not represent the concurrent, relational, migration-driven platform target.

## Decision

Use PostgreSQL 16 as the primary persistent store, SQLAlchemy 2 for mapping, and Alembic as the sole schema migration mechanism. SQLite remains permitted only for isolated metadata tests.

## Consequences

Relations, JSON audit payloads, SQL marts, and future pgvector retrieval share a governed store. Local execution now requires Docker or PostgreSQL.

