# ADR-003: Deterministic pass/fail decisions

## Context

LLMs can assist requirement analysis, test drafting, and RCA but are not reliable execution oracles.

## Decision

Only deterministic rules, SQL checks, and configured numeric policies decide pass/fail. AI-generated assets begin in review-required states and cannot activate themselves.

## Consequences

Outcomes are reproducible, auditable, and safe to use in CI. AI remains useful without becoming an untraceable quality gate.

