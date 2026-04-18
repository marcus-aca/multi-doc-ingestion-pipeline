# Submission Readiness Checker

This Lambda evaluates whether a submission can move from `WAITING_FOR_INDEX` to `READY`.

Inputs:

- `submissionId`
- optional `documentIds`

Behavior:

- loads the referenced `documentId`s from the event or `SubmissionRegistry`
- reads each document from `DocumentRegistry`
- if any document is `FAILED`, marks the submission `FAILED`
- if all documents are `INDEXED`, marks the submission `READY` and sets `readyAt`
- otherwise marks the submission `WAITING_FOR_INDEX`

The function emits structured JSON logs so Step Functions, Lambda logs, and DynamoDB state can be correlated with:

- `submissionId`
- `documentIds`
- per-document ingestion states
- final submission status decision
