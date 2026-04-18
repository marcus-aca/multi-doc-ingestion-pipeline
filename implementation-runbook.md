# Implementation Runbook

This runbook turns the POC design into an implementation sequence with small, testable steps. It assumes:

- AWS access is available
- default AWS region is `us-east-1`
- infrastructure is managed with Terraform
- the Bedrock Knowledge Base will be provisioned as part of this effort
- Amazon Bedrock AgentCore Runtime will be used for the retrieval and summarization path
- Anthropic Claude Sonnet 4.6 will be the Bedrock model used by the AgentCore path
- summarization can remain placeholder logic for now
- the proof goal is:
  - ingest documents only after a submission is complete
  - ingest only new or updated canonical documents through the KB coordinator
  - retrieve only the documents linked to a specific `submissionId`
  - prove scoped search works for each submission

## Success Criteria

- [ ] Files can be uploaded to `ingestion/{submissionId}/{fileId}`
- [ ] A completion event starts submission orchestration
- [ ] Repeated identical raw files are collapsed through `RawFileRegistry`
- [ ] Canonical documents are written once and reused through `DocumentRegistry`
- [ ] KB ingestion is triggered only for new or changed canonical documents
- [ ] Submission status moves to `READY` only when all referenced documents are indexed
- [ ] A test query for `submissionId=A` only returns documents linked to `A`
- [ ] A test query for `submissionId=B` only returns documents linked to `B`
- [ ] AgentCore Runtime call can fetch only the scoped documents for a submission
- [ ] AgentCore Runtime can call Claude Sonnet 4.6 with only the scoped retrieved content

## Phase 0: Project Setup

Phase 0 decisions for this repo:

- use `us-east-1` as the default region
- use local Terraform state for the first pass
- use `mdip-poc` as the default resource naming prefix
- if networking or VPC resources are needed later, create new isolated resources in Terraform rather than attaching to existing shared infrastructure
  - this keeps cleanup simple and avoids side effects on existing environments

- [ ] Create local folders for:
  - `terraform/`
  - `src/lambdas/upload_event_handler/`
  - `src/lambdas/preprocessor/`
  - `src/lambdas/kb_coordinator/`
  - `src/lambdas/query_api/`
  - `scripts/`
- [ ] Decide Terraform state strategy:
  - local state for the first pass, or
  - remote backend if the team already has a standard
- [ ] Decide naming prefix for all AWS resources
- [ ] Confirm AWS region supports Bedrock Knowledge Bases and the chosen foundation model

Validation:

- [ ] `aws sts get-caller-identity` works
- [ ] `aws configure get region` matches intended deployment region
- [ ] `terraform version` is available locally
- [ ] `aws bedrock-agent list-knowledge-bases` or console access confirms KB APIs are available in-region

## Phase 1: Terraform Foundation

- [ ] Create Terraform root module with:
  - provider config
  - common tags
  - variables for region, environment, name prefix
- [ ] Add S3 bucket for documents
- [ ] Add bucket prefixes by convention:
  - `ingestion/`
  - `processed/`
  - `canonical/`
- [ ] Add lifecycle rules:
  - `ingestion/` short retention
  - `processed/` shorter retention
  - `canonical/` retained
- [ ] Add DynamoDB tables:
  - `SubmissionRegistry`
  - `RawFileRegistry`
  - `DocumentRegistry`
  - `IngestionRun`
- [ ] Add IAM roles and policies for:
  - upload event Lambda
  - preprocessor Lambda
  - Step Functions state machine
  - KB coordinator Lambda
  - query API Lambda
  - AgentCore Runtime execution
- [ ] Add CloudWatch log groups

Validation:

- [ ] `terraform init`
- [ ] `terraform plan`
- [ ] `terraform apply`
- [ ] Confirm bucket exists in AWS console
- [ ] Confirm lifecycle rules are visible on the bucket
- [ ] Confirm all DynamoDB tables exist
- [ ] Confirm IAM roles were created with expected trust relationships

## Phase 2: Bedrock KB Integration Baseline

- [ ] Decide whether Terraform will create the KB or reference an existing KB
- [ ] If using an existing KB, add Terraform variables/outputs for:
  - `knowledge_base_id`
  - data source or connector references if needed
- [ ] Add Terraform variables/outputs for:
  - AgentCore Runtime configuration or deployment reference
  - Claude Sonnet 4.6 model ID
- [ ] Confirm KB retrieval works manually before wiring the pipeline
- [ ] Confirm KB ingestion permissions are included in IAM for the coordinator
- [ ] Confirm AgentCore Runtime execution role can invoke Bedrock retrieval and Claude Sonnet 4.6

Validation:

- [ ] Use AWS console or CLI to confirm the KB exists and is active
- [ ] Confirm the application role can call KB retrieval APIs
- [ ] Confirm the coordinator role can call KB ingestion APIs
- [ ] Confirm the AgentCore Runtime role can invoke retrieval and Claude Sonnet 4.6

## Phase 3: Define Registry Schemas and Status Model

- [ ] Document the exact item schema in code comments or README for:
  - `SubmissionRegistry`
  - `RawFileRegistry`
  - `DocumentRegistry`
  - `IngestionRun`
- [ ] Standardize `SubmissionRegistry.status` values, for example:
  - `RECEIVING`
  - `COMPLETE`
  - `WAITING_FOR_INDEX`
  - `READY`
  - `FAILED`
- [ ] Standardize `RawFileRegistry.status` values, for example:
  - `NEW`
  - `PROCESSING`
  - `RESOLVED`
  - `FAILED`
- [ ] Standardize `DocumentRegistry.kbIngestionStatus` values:
  - `NEW`
  - `PENDING_INGESTION`
  - `INGESTING`
  - `INDEXED`
  - `FAILED`
- [ ] Standardize `IngestionRun.status` values:
  - `STARTED`
  - `SUCCEEDED`
  - `FAILED`

Validation:

- [ ] Insert one sample item into each table manually with AWS CLI
- [ ] Read the items back with `aws dynamodb get-item`
- [ ] Confirm the schema shape is easy to query for the expected access patterns
- [ ] Keep sample DynamoDB item payloads in the repo so future phases can reuse them

## Phase 4: Upload Event Handler

- [ ] Implement Lambda to handle S3 object-created events for `ingestion/`
- [ ] Parse `submissionId` and `fileId` from the object key
- [ ] Upsert `SubmissionRegistry` with:
  - incremented `receivedFileCount`
  - file tracking in `fileIds`
  - `status=RECEIVING` if not already terminal
- [ ] Ignore non-`ingestion/` prefixes
- [ ] Add idempotency to avoid double counting repeated S3 events
- [ ] Wire S3 event notification to Lambda

Validation:

- [ ] Upload a file manually to `ingestion/test-submission-1/file-001`
- [ ] Confirm Lambda logs show the event was handled
- [ ] Confirm `SubmissionRegistry` contains `submissionId=test-submission-1`
- [ ] Confirm the `fileId` is recorded only once even if the event is replayed

## Phase 5: Completion Trigger and Step Functions Skeleton

- [ ] Define completion contract:
  - API call, EventBridge event, or completion object
- [ ] For the POC, implement the simplest explicit completion trigger
- [ ] Create Step Functions state machine in Terraform
- [ ] Initial states:
  - `LoadSubmissionState`
  - `ValidateManifestAndFilesPresent`
  - `Success`
- [ ] Add a small trigger Lambda or API route to start the state machine with:
  - `submissionId`
  - expected `fileIds`

Validation:

- [ ] Start one execution manually
- [ ] Confirm the execution can load a submission and validate expected files
- [ ] Confirm the execution fails cleanly when a file is missing

## Phase 6: Raw File Dedupe

- [x] Implement logic in Step Functions task Lambda or dedicated worker to:
  - read `ingestion/{submissionId}/{fileId}`
  - compute `rawFileHash`
- [x] Add `RawFileRegistry` conditional-write claim logic:
  - if missing, create item with `status=PROCESSING`
  - if present and `RESOLVED`, reuse `documentId`
  - if present and `PROCESSING`, wait/retry
- [x] Record `rawFileHash` to `documentId` mapping once resolved
  - For the current checkpoint, this was validated by manually updating the `RawFileRegistry` item to `RESOLVED` with a placeholder `documentId`. Phase 8 will make this transition happen automatically.

Validation:

- [x] Upload the same exact file twice under different `submissionId`s
- [x] Confirm only one flow claims preprocessing ownership
- [x] Confirm a duplicate submission waits/retries and then fails cleanly while the raw file remains unresolved
- [x] Confirm the second flow resolves to the same `documentId`
- [x] Confirm `RawFileRegistry` transitions to `RESOLVED`

## Phase 7: Preprocessing Placeholder

- [x] Implement preprocessing Lambda
- [x] For the POC, keep preprocessing simple:
  - read raw file
  - safe-load JSON input
  - remove any `segment_id` fields recursively
  - convert the sanitized payload into naive Markdown
  - write result to `processed/{submissionId}/{fileId}.md`
  - compute `canonicalHash`
- [x] Include placeholder hooks for OCR or richer normalization later
- [x] Return:
  - `processedS3Key`
  - `canonicalHash`
  - optional extracted metadata

Validation:

- [x] Run preprocessing for one uploaded file
- [x] Confirm `processed/{submissionId}/{fileId}.md` exists
- [x] Confirm the returned `canonicalHash` is stable on repeated runs of the same file

## Phase 8: Canonical Dedupe and Document Registry

- [x] Implement `DocumentRegistry` lookup by `canonicalHash`
- [x] If `canonicalHash` exists:
  - reuse the existing `documentId`
- [x] If `canonicalHash` does not exist:
  - create new `documentId`
  - write canonical chunk files to `canonical/{documentId}/chunk-0001.md`
  - create `DocumentRegistry` item with:
    - `documentId`
    - `canonicalHash`
    - `kbIngestionStatus=PENDING_INGESTION`
    - `isActive=false`
  - For the current checkpoint, optional business-version fields such as `businessDocumentKey`, `sourceVersion`, and `sourceUpdatedAt` are deferred to Phase 9 so GSI-backed attributes are only written when real upstream values exist
- [x] Update `RawFileRegistry` to `RESOLVED`
- [x] Attach `documentId` to the submission
  - The current implementation marks the submission `COMPLETE` after canonical resolution. Submission transitions to `WAITING_FOR_INDEX` and `READY` are still deferred to later phases.

Validation:

- [x] Submit two different raw files that normalize to the same canonical content
- [x] Confirm both resolve to the same `documentId`
- [x] Confirm only one canonical Markdown object is written
- [x] Confirm the submission item lists the correct `documentId`s

## Phase 9: Active Document Rule

- [x] Implement the rule:
  - latest upstream submission is active for a given `businessDocumentKey`
- [x] Compare using `sourceVersion` or `sourceUpdatedAt`
- [x] When a newer canonical document is accepted:
  - mark the new record `isActive=true`
  - mark the previous active record `isActive=false`
- [x] Do not change the `documentId` stored on older submissions
- [x] For the current sample-driven implementation:
  - derive `businessDocumentKey` from JSON `report_id`
  - derive `sourceUpdatedAt` from JSON `report_date`
  - treat the latest submission as active if ordering data is missing

Validation:

- [x] Submit version 1 of a business document
- [x] Submit version 2 of the same business document
- [x] Confirm the newer record is active
- [x] Confirm the old submission still references the older `documentId`
- [x] Confirm the new submission references the newer `documentId`

## Phase 10: KB Coordinator for S3-Backed Ingestion

- [x] Implement KB coordinator Lambda
- [x] Trigger it on an EventBridge schedule, for example every 5 minutes
- [x] Coordinator behavior:
  - find `DocumentRegistry` items where `kbIngestionStatus=PENDING_INGESTION`
  - if no work, exit
  - create `IngestionRun`
  - update selected documents to `INGESTING`
  - call `StartIngestionJob` for the S3-backed Knowledge Base
  - record `kbOperationId`
  - poll or revisit later for completion
  - on success mark docs `INDEXED`
  - on failure mark docs `FAILED` and store error summary
- [x] Ensure coordinator does not start overlapping ingestion for the same pending set
- [x] Safe behavior when KB configuration is missing:
  - log the pending document set
  - return without mutating document ingestion state

Validation:

- [x] Run the coordinator manually
- [x] Confirm it returns a structured `kb_coordinator_missing_configuration` result while `knowledge_base_id` and `knowledge_base_data_source_id` are unset
- [x] Confirm the coordinator log group records the selected pending document IDs
- [ ] After configuring a real Knowledge Base and data source:
  - confirm an `IngestionRun` item is created
  - confirm document state moves from `PENDING_INGESTION` to `INGESTING`
  - confirm eventual transition to `INDEXED` or `FAILED`

Implementation findings from the current POC:

- [x] Provisioned the Knowledge Base and S3 data source in Terraform using Amazon S3 Vectors
- [x] Enabled Knowledge Base log delivery in Terraform to CloudWatch Logs
- [x] Reduced canonical metadata sidecars to a plain S3 metadata file containing only `documentId`
- [x] Recreated the S3 vector index with `AMAZON_BEDROCK_TEXT` and `AMAZON_BEDROCK_METADATA` configured as non-filterable metadata keys
- [x] Confirmed `StartIngestionJob` can be started and polled with real `IngestionRun` state
- [x] Added coordinator logging for:
  - selected `documentId`s
  - canonical prefix and chunk count
  - raw Bedrock ingestion response payload
  - raw Bedrock poll response payload
- [x] Confirmed a tiny manual Markdown document with a minimal `.metadata.json` sidecar can be indexed successfully
- [x] Confirmed the original S3 vector index configuration failed on larger chunks with `Filterable metadata must have at most 2048 bytes`
- [x] Confirmed the non-filterable metadata-key fix resolves the issue for:
  - a tiny manual Markdown chunk
  - a plain-text chunk of roughly `4,000` characters
  - a realistic pipeline-generated document split into `192` canonical Markdown chunks
- [x] Confirmed the coordinator transitions a realistic document from `PENDING_INGESTION` to `INGESTING` to `INDEXED`

## Phase 11: Submission Readiness

- [x] Extend Step Functions to:
  - wait
  - re-check all `documentId`s linked to the submission
  - continue only when all are `INDEXED`
- [x] Mark submission `READY`
- [x] Emit ready callback payload

Validation:

- [x] Run a full submission with 1-2 new docs
- [x] Confirm submission does not move to `READY` before doc indexing completes
- [x] Confirm submission becomes `READY` after all referenced docs are `INDEXED`

## Phase 12: External Ready Callback

- [x] Implement callback Lambda as the POC-ready external callback target
- [x] Send:
  - `submissionId`
  - `status=READY`
  - timestamp
- [x] Record callback result in `SubmissionRegistry.callbackStatus`
- [ ] Add retries with backoff
  - The current POC uses a mock Lambda target and records successful delivery. Retry and DLQ behavior remain a later hardening step.

Validation:

- [x] Point callback at a test endpoint such as webhook.site or a temporary API Gateway mock
  - For the current POC, the callback target is a dedicated mock Lambda.
- [x] Confirm payload is received once the submission becomes `READY`
- [ ] Confirm failed callbacks retry and then mark failure state if needed

## Phase 13: AgentCore Scoped Query Path

- [x] Implement a scoped query entry point
  - The current POC uses a direct Lambda wrapper that preserves the same submission-scoping model the future AgentCore Runtime path will use.
- [x] Inputs:
  - `submissionId`
  - query text
- [x] Read `documentId`s from `SubmissionRegistry`
- [x] Call Bedrock KB retrieval with metadata filters limited to those `documentId`s
- [x] Pass the scoped retrieved content to Claude Sonnet 4.6 through Amazon Bedrock model invocation
  - The current implementation invokes Sonnet 4.6 through the Bedrock inference profile `us.anthropic.claude-sonnet-4-6`.
- [x] Return:
  - retrieved document ids
  - snippets or matches
  - placeholder summary text

For now, placeholder summary behavior is enough, for example:

- `"Summary placeholder from AgentCore. Retrieved N scoped documents for submission X."`

Validation:

- [x] Create two submissions with different docs
- [x] Query submission A for a term that only exists in A
- [x] Confirm only A documents are returned
- [x] Query submission B for a term that only exists in B
- [x] Confirm only B documents are returned
- [x] Query A for a term that exists only in B
- [x] Confirm no B documents leak into the results
- [x] Confirm the model prompt only includes scoped retrieved content for the requested submission

## Traceability Standard For All Phases

- [ ] Every Lambda logs structured JSON rather than relying on free-form strings
- [ ] Every log line includes the strongest available identifiers for that step
- [ ] At minimum, include:
  - `submissionId`
  - `fileId` when relevant
  - `executionArn` when relevant
  - `expectedFileIds` for completion/validation
  - `rawFileHash` when available
  - `canonicalHash` when available
  - `documentId` when available
  - `ingestionRunId` when available
- [ ] Step Functions execution logging remains enabled with execution data
- [ ] DynamoDB state transitions and CloudWatch logs together can explain:
  - what arrived
  - what was deduped
  - what was preprocessed
  - what canonical document was chosen
  - what was directly ingested
  - what was returned for a scoped query

Validation:

- [ ] For one submission, trace the path from S3 upload to final workflow result using only CloudWatch logs and DynamoDB state
- [ ] Confirm each major step has enough identifiers to join the story together without guesswork

## Phase 14: End-to-End POC Script

- [x] Create helper scripts under `scripts/` to:
  - upload test files
  - trigger completion
  - poll submission status
  - invoke AgentCore Runtime
- [x] Prepare sample data sets:
  - submission A with 2 docs
  - submission B with 2 different docs
  - submission C reusing one exact raw file from A
  - submission D reusing one canonical doc with different raw formatting
  - submission E as an updated business document

Validation:

- [x] Run all sample submissions end to end
- [x] Confirm raw duplicate reuse for C
- [x] Confirm canonical reuse for D
- [x] Confirm newer business doc becomes active for E
- [x] Confirm scoped retrieval still works per submission

## Phase 15: Operational Hardening

- [x] Add CloudWatch alarms for:
  - failed Step Functions executions
  - failed coordinator runs
  - documents stuck in `INGESTING`
  - submissions stuck in non-terminal states
- [x] Add dead-letter or manual review path for repeated failures
- [x] Add dashboards for:
  - submissions by status
  - Knowledge Base ingestion runs by status
  - callback failures
- [x] Add structured logging with correlation fields:
  - `submissionId`
  - `fileId`
  - `rawFileHash`
  - `canonicalHash`
  - `documentId`
  - `ingestionRunId`

Validation:

- [x] Force one failed preprocessing case
- [x] Force one failed callback case
- [x] Confirm alarms or logs make root cause easy to find

## Phase 16: POC Exit Checklist

- [x] Terraform can create the environment from scratch
- [x] One manual test submission completes successfully
- [x] One duplicate raw file is reused correctly
- [x] One canonical duplicate is reused correctly
- [x] One business document update becomes active correctly
- [x] One Knowledge Base ingestion run successfully indexes changed docs
- [x] One AgentCore Runtime scoped retrieval proves document isolation by `submissionId`
- [x] AgentCore Runtime can invoke Claude Sonnet 4.6 using only scoped retrieval results

Current Phase 16 validation notes:

- `scripts/validate_phase16.py --validated-fresh-create` validated the checklist items above against a freshly destroyed and recreated stack with run id `codexphase16fresh`
- Terraform destroy/apply from scratch now succeeds, with the Bedrock KB teardown hardened by switching the data source template to `DataDeletionPolicy: RETAIN`
- Sonnet invocation succeeds against the scoped-query validation path on the rebuilt stack
- Team walkthrough remains a manual team process item rather than an automated repo check


## Nice-to-Have Later

- [ ] Replace placeholder preprocessing with richer parsers/OCR
- [ ] Replace placeholder summary with richer AgentCore prompt orchestration
- [ ] Add reconciliation job for rare KB/S3 drift recovery
- [ ] Move submission-document mapping into a dedicated table if submission size grows
