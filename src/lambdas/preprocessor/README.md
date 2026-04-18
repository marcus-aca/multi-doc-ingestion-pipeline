# Preprocessor Lambda

This Lambda provides the Phase 7 preprocessing placeholder for the POC.

Responsibilities:

- read the raw file from `ingestion/{submissionId}/{fileId}`
- safely parse the raw file as JSON
- remove any `segment_id` fields recursively
- render the sanitized JSON into a stable Markdown representation
- write a processed Markdown artifact to `processed/{submissionId}/{fileId}.md`
- compute `canonicalHash` from normalized business content, not submission metadata
- update `RawFileRegistry` with `processedS3Key` and `canonicalHash`

Current placeholder behavior:

- expect UTF-8 JSON input
- fail fast if the payload is not valid JSON
- remove `segment_id` keys at any nesting level
- convert dictionaries, lists, and scalar values into naive Markdown
- store the processed artifact as actual Markdown text, not a JSON envelope
- derive optional business metadata from known JSON fields when available:
  - `businessDocumentKey` from `report_id`
  - `sourceUpdatedAt` from `report_date`
- no schema-specific extraction or chunk-aware formatting yet

Expected event shape:

```json
{
  "submissionId": "sub-001",
  "fileId": "file-001",
  "rawFileHash": "sha256:..."
}
```

Return shape:

```json
{
  "action": "preprocessing_completed",
  "submissionId": "sub-001",
  "fileId": "file-001",
  "rawFileHash": "sha256:...",
  "processedS3Key": "processed/sub-001/file-001.md",
  "canonicalHash": "sha256:...",
  "normalizationStrategy": "json_to_markdown_v1",
  "businessDocumentKey": "sample-001",
  "sourceVersion": null,
  "sourceUpdatedAt": "2026-04-17",
  "extractedMetadata": {
    "byteCount": 123,
    "topLevelType": "dict",
    "topLevelEntryCount": 6,
    "segmentIdRemovedCount": 4,
    "sanitizedTopLevelEntryCount": 6,
    "businessDocumentKey": "sample-001",
    "sourceVersion": null,
    "sourceUpdatedAt": "2026-04-17",
    "characterCount": 120,
    "lineCount": 4
  }
}
```
