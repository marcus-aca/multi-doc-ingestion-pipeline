# Canonical Resolver Lambda

This Lambda provides the Phase 8 canonical document resolution step for the POC.

Responsibilities:

- read the processed Markdown document from `processed/{submissionId}/{fileId}.md`
- look up `DocumentRegistry` by `canonicalHash`
- reuse the existing `documentId` when normalized content is already known
- otherwise create a deterministic `documentId`, write plain Markdown to `canonical/{documentId}.md`, and create a `DocumentRegistry` record
- update `RawFileRegistry` to `RESOLVED`

Canonical storage rule:

- `canonical/` contains only ingestible Markdown content
- canonical metadata remains in `DocumentRegistry`
- pipeline metadata is not embedded in the canonical file body

Expected event shape:

```json
{
  "submissionId": "sub-001",
  "fileId": "file-001",
  "rawFileHash": "sha256:...",
  "processedS3Key": "processed/sub-001/file-001.md",
  "canonicalHash": "sha256:...",
  "businessDocumentKey": "sample-001",
  "sourceVersion": null,
  "sourceUpdatedAt": "2026-04-17",
  "normalizationStrategy": "json_to_markdown_v1",
  "extractedMetadata": {
    "byteCount": 123,
    "topLevelType": "dict"
  }
}
```

Return shape:

```json
{
  "action": "canonical_document_created",
  "submissionId": "sub-001",
  "fileId": "file-001",
  "rawFileHash": "sha256:...",
  "processedS3Key": "processed/sub-001/file-001.md",
  "canonicalHash": "sha256:...",
  "documentId": "doc-1234abcd5678ef90",
  "canonicalS3Key": "canonical/doc-1234abcd5678ef90.md",
  "reusedExistingDocument": false,
  "kbIngestionStatus": "PENDING_INGESTION",
  "businessDocumentKey": "sample-001",
  "sourceVersion": null,
  "sourceUpdatedAt": "2026-04-17",
  "isActive": true
}
```
