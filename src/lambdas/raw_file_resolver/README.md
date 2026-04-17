# Raw File Resolver

This Lambda handles Phase 6 raw-file dedupe.

Responsibilities:

- read `ingestion/{submissionId}/{fileId}` from S3
- compute `rawFileHash` using SHA-256 over the raw object bytes
- claim a `RawFileRegistry` item using a conditional write
- detect whether the same raw payload is already being processed or has already been resolved

Return shape:

```json
{
  "action": "raw_file_claimed",
  "submissionId": "sub-001",
  "fileId": "file-001",
  "rawFileHash": "sha256:...",
  "rawFileStatus": "PROCESSING",
  "ownershipClaimed": true,
  "reusedExistingDocument": false,
  "documentId": null
}
```
