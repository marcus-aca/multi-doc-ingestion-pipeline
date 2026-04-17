# Upload Event Handler

This Lambda is triggered by S3 object-created events for the `ingestion/` prefix.

Responsibilities:

- parse `submissionId` and `fileId` from `ingestion/{submissionId}/{fileId}`
- idempotently upsert `SubmissionRegistry`
- increment `receivedFileCount` only when the `fileId` is new for the submission
- ignore duplicate S3 notifications for the same file
