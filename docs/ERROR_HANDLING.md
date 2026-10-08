# Error Handling

## API

400 validation; 401 authentication; 403 authorization; 404 not found; 409 conflict; 429 rate limit; 500 unexpected error.

## AI

Provider timeout → retry if safe.
Provider failure → preserve incident and allow manual workflow.
Insufficient evidence → do not guess.
Agent conflict → preserve outputs and request human review.

## UX

All long-running AI operations show stage/status, not an unexplained spinner.
