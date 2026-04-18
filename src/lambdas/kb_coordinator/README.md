# KB Coordinator Lambda

This Lambda provides the Phase 10 direct-ingestion coordination step for the POC.

Responsibilities:

- find canonical documents waiting for Knowledge Base ingestion
- avoid overlapping ingestion runs
- create and update `IngestionRun` records
- call Bedrock direct ingestion for `canonical/{documentId}.md`
- poll in-flight ingestion runs on later invocations
- keep ingestion metadata in `DocumentRegistry`

Current behavior:

- if a `STARTED` `IngestionRun` exists, poll Bedrock document statuses
- otherwise batch up to the configured number of `PENDING_INGESTION` documents
- if `knowledge_base_id` or `data_source_id` is not configured, exit safely without mutating document state
- when configured, send S3-backed direct-ingestion requests with inline metadata attributes

Expected event shape:

```json
{}
```

Example result when KB is not configured:

```json
{
  "action": "kb_coordinator_missing_configuration",
  "documentCount": 3,
  "documentIds": ["doc-001", "doc-002", "doc-003"],
  "knowledgeBaseConfigured": false
}
```
