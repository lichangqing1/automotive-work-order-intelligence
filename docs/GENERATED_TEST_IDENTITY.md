# Generated test identity

AI-provider `test_id` values are display identifiers and generation provenance,
not database keys. Every accepted generated occurrence receives a platform-owned
`TestCase.test_case_id` and `TestCaseVersion.test_case_version_id`. The provider
value remains in both JSON specifications as `test_id` and
`provider_test_id`, and traceability responses expose `provider_test_id`.

Repeated generation creates a new independent test case at version 1. A model
generation is a new stochastic artifact, not an edit of an existing reviewed
test. Multiple records with the same provider ID are therefore retained when
their scenarios are otherwise reviewable; title-based validation continues to
reject exact duplicate scenarios explicitly.

## Database compatibility

No schema migration is required. Existing platform primary keys already enforce
global uniqueness, while `TestCaseVersion` foreign keys preserve requirement,
parent, and AI-run associations. Test results continue to reference the exact
parent and version that were executed. Provider identity is stored in existing
JSON columns, so no column or constraint change is needed.

Historical records are not rewritten. Databases created before this correction
should be checked for a parent associated with more than one requirement:

```sql
SELECT test_case_id, COUNT(DISTINCT requirement_version_id)
FROM test_case_versions
GROUP BY test_case_id
HAVING COUNT(DISTINCT requirement_version_id) > 1;
```

Any result requires manual reconciliation against review and execution history;
the application cannot safely infer whether an old shared parent was intentional.
