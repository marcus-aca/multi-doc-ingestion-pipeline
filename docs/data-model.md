# Data Model

This document defines the canonical registry shapes and status values for the POC.

## Status Enums

### SubmissionRegistry.status

- `RECEIVING`
- `COMPLETE`
- `WAITING_FOR_INDEX`
- `READY`
- `FAILED`

### RawFileRegistry.status

- `NEW`
- `PROCESSING`
- `RESOLVED`
- `FAILED`

### DocumentRegistry.kbIngestionStatus

- `NEW`
- `PENDING_INGESTION`
- `INGESTING`
- `INDEXED`
- `FAILED`

### IngestionRun.status

- `STARTED`
- `SUCCEEDED`
- `FAILED`

## SubmissionRegistry

Purpose:

- tracks one external submission lifecycle
- records which file arrivals and canonical documents belong to that submission

Primary key:

- `submissionId` (string)

Suggested item shape:

```json
{
  "submissionId": "sub-001",
  "externalRequestId": "req-001",
  "status": "RECEIVING",
  "expectedFileCount": 2,
  "receivedFileCount": 1,
  "manifestReceived": false,
  "ingestionPrefix": "ingestion/sub-001/",
  "fileIds": ["file-001"],
  "documentIds": [],
  "readyAt": null,
  "callbackStatus": null,
  "createdAt": "2026-04-17T00:00:00Z",
  "updatedAt": "2026-04-17T00:00:00Z"
}
```

Access patterns:

- get submission by `submissionId`
- update file receipt progress
- update document membership
- check readiness state

## RawFileRegistry

Purpose:

- collapses repeated identical raw uploads before expensive preprocessing
- maps exact raw file bytes to the resolved canonical document

Primary key:

- `rawFileHash` (string)

Suggested item shape:

```json
{
  "rawFileHash": "sha256:raw-abc123",
  "status": "RESOLVED",
  "processedS3Key": "processed/sub-001/file-001",
  "canonicalHash": "sha256:canon-xyz789",
  "documentId": "doc-001",
  "firstSeenAt": "2026-04-17T00:00:00Z",
  "lastSeenAt": "2026-04-17T00:05:00Z",
  "updatedAt": "2026-04-17T00:05:00Z"
}
```

Access patterns:

- get by `rawFileHash`
- conditionally create ownership record during preprocessing
- resolve duplicate raw file to `documentId`

## DocumentRegistry

Purpose:

- stores the canonical document identity after preprocessing
- tracks direct-ingestion lifecycle
- tracks latest active document for a `businessDocumentKey`

Primary key:

- `documentId` (string)

Secondary indexes:

- `canonicalHash-index`
- `businessDocumentKey-index`

Suggested item shape:

```json
{
  "documentId": "doc-001",
  "canonicalHash": "sha256:canon-xyz789",
  "businessDocumentKey": "business-doc-123",
  "sourceVersion": "7",
  "canonicalS3Key": "canonical/doc-001",
  "kbIngestionStatus": "INDEXED",
  "pendingIngestionRunId": null,
  "lastSuccessfulIngestionRunId": "run-001",
  "lastIngestionError": null,
  "isActive": true,
  "createdAt": "2026-04-17T00:01:00Z",
  "updatedAt": "2026-04-17T00:10:00Z"
}
```

Access patterns:

- get by `documentId`
- find canonical duplicate by `canonicalHash`
- find latest document for a `businessDocumentKey`
- find documents waiting for direct ingestion

## IngestionRun

Purpose:

- tracks one KB direct ingestion batch
- ties a set of `documentId`s to one coordinator-managed operation

Primary key:

- `ingestionRunId` (string)

Suggested item shape:

```json
{
  "ingestionRunId": "run-001",
  "status": "STARTED",
  "kbOperationId": "kb-op-001",
  "documentIds": ["doc-001", "doc-002"],
  "startedAt": "2026-04-17T00:02:00Z",
  "completedAt": null,
  "errorSummary": null
}
```

Access patterns:

- get ingestion run by `ingestionRunId`
- inspect direct ingestion outcome for a set of documents

## Business Rules

- raw duplicate reuse is keyed by `rawFileHash`
- canonical reuse is keyed by `canonicalHash`
- latest upstream business document submission is active for a given `businessDocumentKey`
- submission-scoped retrieval always uses `documentId`, not `isActive`
