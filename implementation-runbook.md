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
  - directly ingest only new or updated canonical documents
  - retrieve only the documents linked to a specific `submissionId`
  - prove scoped search works for each submission

## Success Criteria

- [ ] Files can be uploaded to `ingestion/{submissionId}/{fileId}`
- [ ] A completion event starts submission orchestration
- [ ] Repeated identical raw files are collapsed through `RawFileRegistry`
- [ ] Canonical documents are written once and reused through `DocumentRegistry`
- [ ] Direct ingestion into Bedrock KB is triggered only for new or changed canonical documents
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
- [ ] Confirm direct ingestion API permissions are included in IAM for the coordinator
- [ ] Confirm AgentCore Runtime execution role can invoke Bedrock retrieval and Claude Sonnet 4.6

Validation:

- [ ] Use AWS console or CLI to confirm the KB exists and is active
- [ ] Confirm the application role can call KB retrieval APIs
- [ ] Confirm the coordinator role can call direct ingestion APIs
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

- [ ] Implement preprocessing Lambda
- [ ] For the POC, keep preprocessing simple:
  - read raw file
  - convert to normalized text or a simple structured payload
  - write result to `processed/{submissionId}/{fileId}`
  - compute `canonicalHash`
- [ ] Include placeholder hooks for OCR or richer normalization later
- [ ] Return:
  - `processedS3Key`
  - `canonicalHash`
  - optional extracted metadata

Validation:

- [ ] Run preprocessing for one uploaded file
- [ ] Confirm `processed/{submissionId}/{fileId}` exists
- [ ] Confirm the returned `canonicalHash` is stable on repeated runs of the same file

## Phase 8: Canonical Dedupe and Document Registry

- [ ] Implement `DocumentRegistry` lookup by `canonicalHash`
- [ ] If `canonicalHash` exists:
  - reuse the existing `documentId`
- [ ] If `canonicalHash` does not exist:
  - create new `documentId`
  - write canonical content to `canonical/{documentId}`
  - create `DocumentRegistry` item with:
    - `documentId`
    - `canonicalHash`
    - `businessDocumentKey`
    - `sourceVersion` or `sourceUpdatedAt`
    - `kbIngestionStatus=PENDING_INGESTION`
    - `isActive=false`
- [ ] Update `RawFileRegistry` to `RESOLVED`
- [ ] Attach `documentId` to the submission

Validation:

- [ ] Submit two different raw files that normalize to the same canonical content
- [ ] Confirm both resolve to the same `documentId`
- [ ] Confirm only one canonical object is written
- [ ] Confirm the submission item lists the correct `documentId`s

## Phase 9: Active Document Rule

- [ ] Implement the rule:
  - latest upstream submission is active for a given `businessDocumentKey`
- [ ] Compare using `sourceVersion` or `sourceUpdatedAt`
- [ ] When a newer canonical document is accepted:
  - mark the new record `isActive=true`
  - mark the previous active record `isActive=false`
- [ ] Do not change the `documentId` stored on older submissions

Validation:

- [ ] Submit version 1 of a business document
- [ ] Submit version 2 of the same business document
- [ ] Confirm the newer record is active
- [ ] Confirm the old submission still references the older `documentId`
- [ ] Confirm the new submission references the newer `documentId`

## Phase 10: KB Coordinator for Direct Ingestion

- [ ] Implement KB coordinator Lambda
- [ ] Trigger it on an EventBridge schedule, for example every 5 minutes
- [ ] Coordinator behavior:
  - find `DocumentRegistry` items where `kbIngestionStatus=PENDING_INGESTION`
  - if no work, exit
  - create `IngestionRun`
  - update selected documents to `INGESTING`
  - read `canonical/{documentId}` content
  - call Bedrock direct ingestion for those documents
  - record `kbOperationId`
  - poll or revisit later for completion
  - on success mark docs `INDEXED`
  - on failure mark docs `FAILED` and store error summary
- [ ] Ensure coordinator does not start overlapping ingestion for the same pending set

Validation:

- [ ] Create one pending document manually in `DocumentRegistry`
- [ ] Run the coordinator manually
- [ ] Confirm an `IngestionRun` item is created
- [ ] Confirm document state moves from `PENDING_INGESTION` to `INGESTING`
- [ ] Confirm eventual transition to `INDEXED` or `FAILED`

## Phase 11: Submission Readiness

- [ ] Extend Step Functions to:
  - wait
  - re-check all `documentId`s linked to the submission
  - continue only when all are `INDEXED`
- [ ] Mark submission `READY`
- [ ] Emit ready callback payload

Validation:

- [ ] Run a full submission with 1-2 new docs
- [ ] Confirm submission does not move to `READY` before doc indexing completes
- [ ] Confirm submission becomes `READY` after all referenced docs are `INDEXED`

## Phase 12: External Ready Callback

- [ ] Implement callback Lambda or built-in Step Functions task
- [ ] Send:
  - `submissionId`
  - `status=READY`
  - timestamp
- [ ] Add retries with backoff
- [ ] Record callback result in `SubmissionRegistry.callbackStatus`

Validation:

- [ ] Point callback at a test endpoint such as webhook.site or a temporary API Gateway mock
- [ ] Confirm payload is received once the submission becomes `READY`
- [ ] Confirm failed callbacks retry and then mark failure state if needed

## Phase 13: AgentCore Scoped Query Path

- [ ] Implement AgentCore Runtime entry point or wrapper API that calls AgentCore Runtime
- [ ] Inputs:
  - `submissionId`
  - query text
- [ ] Read `documentId`s from `SubmissionRegistry`
- [ ] In AgentCore Runtime, call Bedrock KB retrieval with metadata filters limited to those `documentId`s
- [ ] Pass the scoped retrieved content to Claude Sonnet 4.6 through Amazon Bedrock model invocation
- [ ] Return:
  - retrieved document ids
  - snippets or matches
  - placeholder summary text

For now, placeholder summary behavior is enough, for example:

- `"Summary placeholder from AgentCore. Retrieved N scoped documents for submission X."`

Validation:

- [ ] Create two submissions with different docs
- [ ] Query submission A for a term that only exists in A
- [ ] Confirm only A documents are returned
- [ ] Query submission B for a term that only exists in B
- [ ] Confirm only B documents are returned
- [ ] Query A for a term that exists only in B
- [ ] Confirm no B documents leak into the results
- [ ] Confirm the AgentCore Runtime prompt only includes scoped retrieved content for the requested submission

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

- [ ] Create helper scripts under `scripts/` to:
  - upload test files
  - trigger completion
  - poll submission status
  - invoke AgentCore Runtime
- [ ] Prepare sample data sets:
  - submission A with 2 docs
  - submission B with 2 different docs
  - submission C reusing one exact raw file from A
  - submission D reusing one canonical doc with different raw formatting
  - submission E as an updated business document

Validation:

- [ ] Run all sample submissions end to end
- [ ] Confirm raw duplicate reuse for C
- [ ] Confirm canonical reuse for D
- [ ] Confirm newer business doc becomes active for E
- [ ] Confirm scoped retrieval still works per submission

## Phase 15: Operational Hardening

- [ ] Add CloudWatch alarms for:
  - failed Step Functions executions
  - failed coordinator runs
  - documents stuck in `INGESTING`
  - submissions stuck in non-terminal states
- [ ] Add dead-letter or manual review path for repeated failures
- [ ] Add dashboards for:
  - submissions by status
  - direct ingestion runs by status
  - callback failures
- [ ] Add structured logging with correlation fields:
  - `submissionId`
  - `fileId`
  - `rawFileHash`
  - `canonicalHash`
  - `documentId`
  - `ingestionRunId`

Validation:

- [ ] Force one failed preprocessing case
- [ ] Force one failed callback case
- [ ] Confirm alarms or logs make root cause easy to find

## Phase 16: POC Exit Checklist

- [ ] Terraform can create the environment from scratch
- [ ] One manual test submission completes successfully
- [ ] One duplicate raw file is reused correctly
- [ ] One canonical duplicate is reused correctly
- [ ] One business document update becomes active correctly
- [ ] One direct ingestion run successfully indexes changed docs
- [ ] One AgentCore Runtime scoped retrieval proves document isolation by `submissionId`
- [ ] AgentCore Runtime can invoke Claude Sonnet 4.6 using only scoped retrieval results
- [ ] Team walkthrough completed and open issues captured

## Suggested Execution Order

- [ ] Complete Phases 0-3 first
- [ ] Build and test Phases 4-5 together
- [ ] Build and test Phases 6-9 together
- [ ] Build and test Phases 10-11 together
- [ ] Finish with Phases 12-16

## Nice-to-Have Later

- [ ] Replace placeholder preprocessing with richer parsers/OCR
- [ ] Replace placeholder summary with richer AgentCore prompt orchestration
- [ ] Add reconciliation job for rare KB/S3 drift recovery
- [ ] Move submission-document mapping into a dedicated table if submission size grows
