# ADR-001: Modular monolith before microservices

## Context

The platform has distinct work-order, data-quality, testing, retrieval, AI, and evaluation concerns, but a portfolio deployment does not justify independently operated services for each domain.

## Decision

Use a modular monolith with explicit domain/application/infrastructure/API boundaries. Long-running work may later execute in Celery workers without splitting domain ownership.

## Alternatives

- Microservices: rejected because operational complexity would obscure quality-engineering depth.
- Flat scripts: rejected because business logic would remain coupled to interfaces.

## Consequences

The code is independently testable and can evolve toward services if scaling evidence demands it, while local development remains simple.

