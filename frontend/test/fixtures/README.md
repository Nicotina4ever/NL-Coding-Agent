# Catalog acceptance fixtures

Two isolated fixtures are preserved so the engine and the tests can be judged
separately.

## `catalog-original-strict`

The first realistic Gate C attempt. It contains the original catalog package
(`catalog/models.py`, `catalog/repository.py`, `catalog/service.py`,
`catalog/api.py`) and `tests/test_catalog.py`, whose reservation tests start red.
This fixture was **not simplified** after the engine failures. It is retained as
the reference for honest re-testing of the same mission once the diagnosed
causes are fixed.

## `catalog-reservation`

The second iteration used for the last end-to-end attempts. The goal was narrowed
to three **new** reservation modules
(`catalog/reservation_repository.py`, `catalog/reservation_service.py`,
`catalog/reservation_api.py`) and the tests were rewritten to call the service
through explicit constructors rather than a `bootstrap()` helper. This is a
**test simplification** adopted to reduce model-level API ambiguity; it is not
evidence that the original multi-file rewrite mission was solved.

Run data, staged candidates and logs for every attempt remain under
`.workspace/temp/frontend-accept/` (ignored by Git). The latest result was
`failed` before review, so neither fixture has a completed acceptance record.
