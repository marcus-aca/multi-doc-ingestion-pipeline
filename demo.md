# Demo Walkthrough: Testing The Deployed POC

This document explains how to demo the deployed multi-document ingestion POC using one of the sample manifests, and what each step means in terms of the architecture, workflow, data model, and AWS resources.

The goal is not just to run commands, but to understand what the system is proving at each stage.

## Recommended Demo Input

Use the existing manifest:

- `sample/submissions/submission_a.json`

That manifest uploads two sample files:

- `sample/warehouse_robotics_us.json`
- `sample/vertical_farming_us.json`

It renders the submission ID from:

- `submissionIdTemplate = "phase14-a-{run_id}"`

So if:

```bash
export RUN_ID=demo01
export MANIFEST=sample/submissions/submission_a.json
export SUBMISSION_ID=phase14-a-$RUN_ID
```

then the effective submission ID is:

- `phase14-a-demo01`

## Architecture Context

This demo exercises the full POC path:

1. raw files arrive in S3
2. upload events create submission receipt state
3. an explicit completion trigger starts orchestration
4. files are deduped, preprocessed, and canonically resolved
5. documents are linked to the submission
6. Bedrock indexing is coordinated separately
7. the submission becomes `READY`
8. scoped retrieval and model summarization are tested against only that submission’s documents

In architecture terms, the demo crosses these major components:

- S3
- Lambda
- Step Functions
- DynamoDB
- Bedrock Knowledge Base
- Bedrock model invocation
- CloudWatch logs and metrics

## Core Concepts To Keep In Mind

These fields are the backbone of the design:

- `submissionId`
  - one external user action containing one or more files
- `fileId`
  - one uploaded file within a submission
- `rawFileHash`
  - SHA-256 hash of exact uploaded bytes
- `canonicalHash`
  - hash of normalized business content after preprocessing
- `documentId`
  - internal canonical document version
- `businessDocumentKey`
  - logical external document identity, used to group versions
- `kbIngestionStatus`
  - document-level indexing state in Bedrock

These are intentionally separate because the POC is proving that:

- exact duplicate delivery is not the same thing as canonical content reuse
- canonical content reuse is not the same thing as business document versioning
- submission readiness is not the same thing as file arrival

## Step 0: Inspect The Manifest

Command:

```bash
sed -n '1,200p' "$MANIFEST"
```
```
{
  "label": "A",
  "submissionIdTemplate": "phase14-a-{run_id}",
  "files": [
    {
      "fileId": "warehouse-robotics.json",
      "logicalName": "warehouse_robotics",
      "source": "sample/warehouse_robotics_us.json"
    },
    {
      "fileId": "vertical-farming.json",
      "logicalName": "vertical_farming",
      "source": "sample/vertical_farming_us.json"
    }
  ]
}
```
What this is proving:

- the upstream system expresses a submission as a known set of files
- the POC expects deterministic file membership rather than inferring completeness from timing

What actually matters in the manifest:

- `submissionIdTemplate`
  - how the test submission ID is generated
- `files[*].fileId`
  - the identifiers expected by the completion trigger and the workflow
- `files[*].source`
  - the sample source documents to upload

Why this maps to the design:

- the design explicitly favors completion by manifest or explicit completion event
- this is the architectural boundary between the upstream system and the POC

## Step 1: Upload The Submission Files

Command:

```bash
python3 scripts/upload_test_submission.py "$MANIFEST" --run-id "$RUN_ID"
```
```
{
  "bucket": "mdip-poc-dev-docs-ACCOUNT_ID-us-east-1",
  "files": [
    {
      "byteCount": 1871832,
      "canonicalHash": "sha256:4fd21f3a6eb695578f9bea7ad7c42c8c0ec0cb1e3c71d49dee2394dcfff31ec0",
      "fileId": "warehouse-robotics.json",
      "logicalName": "warehouse_robotics",
      "rawFileHash": "sha256:ef1b62894d762818df28958158944d22318d565e456fc2e37e0720d5e559b496",
      "sourcePath": "/Users/marcus/Working/multi-doc-ingestion-pipeline/sample/warehouse_robotics_us.json",
      "transform": {
        "type": "verbatim"
      }
    },
    {
      "byteCount": 1827671,
      "canonicalHash": "sha256:11e66bb847fb7441d4c89a2bd3808e1f7f083736ac1edfbc0c02246c3fe78d7a",
      "fileId": "vertical-farming.json",
      "logicalName": "vertical_farming",
      "rawFileHash": "sha256:fb1a52bc8f6808302d728c99e3b9c050e49e642d253abb27bade766f95acbd44",
      "sourcePath": "/Users/marcus/Working/multi-doc-ingestion-pipeline/sample/vertical_farming_us.json",
      "transform": {
        "type": "verbatim"
      }
    }
  ],
  "submissionId": "phase14-a-demo01",
  "uploadedKeys": [
    "ingestion/phase14-a-demo01/warehouse-robotics.json",
    "ingestion/phase14-a-demo01/vertical-farming.json"
  ]
}
```
What the script does:

- loads the manifest
- renders the real `submissionId`
- reads each sample file from disk
- computes local file metadata for reporting
- uploads each file to:
  - `ingestion/{submissionId}/{fileId}`

What happens in the POC:

1. objects are written to the S3 document bucket
2. S3 object-created events fire
3. `upload_event_handler` runs for each uploaded file
4. `SubmissionRegistry` is created or updated
5. `fileIds` and `receivedFileCount` are updated idempotently

Relevant architecture components:

- S3 document bucket
- `upload_event_handler` Lambda
- `SubmissionRegistry` DynamoDB table

Important fields at this step:

- `submissionId`
  - identifies the submission record
- `fileId`
  - identifies each uploaded object within the submission
- `ingestionPrefix`
  - usually `ingestion/{submissionId}/`
- `fileIds`
  - tracks which files the submission has received
- `receivedFileCount`
  - count of unique file IDs seen so far
- `status`
  - typically `RECEIVING`

Where to inspect:

S3 raw uploads:

```bash
aws s3api list-objects-v2 \
  --region us-east-1 \
  --bucket mdip-poc-dev-docs-ACCOUNT_ID-us-east-1 \
  --prefix "ingestion/$SUBMISSION_ID/"
```

Submission registry item:

```bash
aws dynamodb get-item \
  --region us-east-1 \
  --table-name mdip-poc-dev-submission-registry \
  --key "{\"submissionId\":{\"S\":\"$SUBMISSION_ID\"}}"
```

Logs:

- `/aws/lambda/mdip-poc-dev-upload-event-handler`

Why this step matters architecturally:

- it proves that receipt tracking is decoupled from orchestration
- file arrival alone does not start heavy downstream processing
- duplicate S3 notifications are tolerated because file membership is tracked idempotently

## Step 2: Trigger Submission Completion

Command:

```bash
python3 scripts/trigger_completion.py "$MANIFEST" --run-id "$RUN_ID"
```
```
{
  "executionArn": "arn:aws:states:us-east-1:ACCOUNT_ID:execution:mdip-poc-dev-submission-orchestration:de776fb5-4389-4260-9374-5a8b1364ddeb",
  "startDate": "2026-04-19T04:17:17.561000+00:00",
  "submissionId": "phase14-a-demo01"
}
```
What the script does:

- recomputes the expected `submissionId`
- derives the expected `fileId` list from the manifest
- waits briefly for upload events to populate `SubmissionRegistry`
- invokes the `completion_trigger` Lambda

What happens in the POC:

1. `completion_trigger` receives:
   - `submissionId`
   - `expectedFileIds`
2. it starts the Step Functions state machine
3. the workflow begins deterministic orchestration for the submission

Relevant architecture components:

- `completion_trigger` Lambda
- Step Functions state machine `mdip-poc-dev-submission-orchestration`
- `submission_validator` Lambda as the first substantive guardrail

Important fields at this step:

- `expectedFileIds`
  - the authoritative list of files expected for this submission
- `executionArn`
  - the Step Functions execution identifier returned by the trigger path
- `submissionId`
  - the join key across S3, DynamoDB, Step Functions, and query testing

Where to inspect:

Step Functions execution:

```bash
aws stepfunctions describe-execution \
  --region us-east-1 \
  --execution-arn "<EXECUTION_ARN>"
```
```
{
    "executionArn": "arn:aws:states:us-east-1:ACCOUNT_ID:execution:mdip-poc-dev-submission-orchestration:de776fb5-4389-4260-9374-5a8b1364ddeb",
    "stateMachineArn": "arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:mdip-poc-dev-submission-orchestration",
    "name": "de776fb5-4389-4260-9374-5a8b1364ddeb",
    "status": "SUCCEEDED",
    "startDate": "2026-04-19T14:17:17.561000+10:00",
    "stopDate": "2026-04-19T14:17:24.002000+10:00",
    "input": "{\"submissionId\": \"phase14-a-demo01\", \"expectedFileIds\": [\"warehouse-robotics.json\", \"vertical-farming.json\"], \"expectedFileCount\": 2}",
    "inputDetails": {
        "included": true
    },
    "output": "{\"submissionId\":\"phase14-a-demo01\",\
    ...
    }
}
```
Submission registry:

```bash
aws dynamodb get-item \
  --region us-east-1 \
  --table-name mdip-poc-dev-submission-registry \
  --key "{\"submissionId\":{\"S\":\"$SUBMISSION_ID\"}}"
```
```
{
    "Item": {
        "callbackDeliveredAt": {
            "S": "2026-04-19T04:17:23.677194Z"
        },
        "callbackStatus": {
            "S": "DELIVERED"
        },
        "createdAt": {
            "S": "2026-04-19T04:12:21.607547Z"
        },
        "documentIds": {
            "L": [
                {
                    "S": "doc-4fd21f3a6eb69557"
                },
                {
                    "S": "doc-9cdf074673dafa3b"
                }
            ]
        },
        "externalRequestId": {
            "S": ""
        },
        "fileIds": {
            "L": [
                {
                    "S": "warehouse-robotics.json"
                },
                {
                    "S": "vertical-farming.json"
                }
            ]
        },
        "ingestionPrefix": {
            "S": "ingestion/phase14-a-demo01/"
        },
        "manifestReceived": {
            "BOOL": false
        },
        "readyAt": {
            "S": "2026-04-19T04:17:22.715746Z"
        },
        "receivedFileCount": {
            "N": "2"
        },
        "status": {
            "S": "READY"
        },
        "submissionId": {
            "S": "phase14-a-demo01"
        },
        "updatedAt": {
            "S": "2026-04-19T04:17:23.677194Z"
        }
    }
}
```
Logs:

- `/aws/lambda/mdip-poc-dev-completion-trigger`
- `/aws/states/mdip-poc-dev-submission-orchestration`
- `/aws/lambda/mdip-poc-dev-submission-validator`

Why this step matters architecturally:

- the design intentionally avoids “quiet-period means complete”
- this is where the POC proves deterministic completion and workflow start conditions
- Step Functions owns orchestration, but DynamoDB remains the workflow source of truth

## Step 3: Process Files Through Dedupe, Preprocessing, and Canonical Resolution

Primary polling command:

```bash
python3 scripts/poll_submission.py "$SUBMISSION_ID" --drive-kb-coordinator
```
```
{
  "executionStatus": null,
  "submission": {
    "callbackDeliveredAt": "2026-04-19T04:17:23.677194Z",
    "callbackStatus": "DELIVERED",
    "createdAt": "2026-04-19T04:12:21.607547Z",
    "documentIds": [
      "doc-4fd21f3a6eb69557",
      "doc-9cdf074673dafa3b"
    ],
    "externalRequestId": "",
    "fileIds": [
      "warehouse-robotics.json",
      "vertical-farming.json"
    ],
    "ingestionPrefix": "ingestion/phase14-a-demo01/",
    "manifestReceived": false,
    "readyAt": "2026-04-19T04:17:22.715746Z",
    "receivedFileCount": "2",
    "status": "READY",
    "submissionId": "phase14-a-demo01",
    "updatedAt": "2026-04-19T04:17:23.677194Z"
  }
}
```

This command is the easiest user-facing way to wait for the workflow, but a lot is happening underneath before the submission reaches terminal state.

### 3A. Raw File Resolution

What happens:

1. `raw_file_resolver` reads each raw object from:
   - `ingestion/{submissionId}/{fileId}`
2. it computes `rawFileHash`
3. it conditionally claims or reuses a `RawFileRegistry` record

What this proves:

- exact duplicate raw uploads can be detected before expensive processing

Important fields:

- `rawFileHash`
- `RawFileRegistry.status`
- `documentId` if a prior exact duplicate already resolved

Where to inspect:

- `/aws/lambda/mdip-poc-dev-raw-file-resolver`
- `mdip-poc-dev-raw-file-registry`

Example inspection:

```bash
aws dynamodb scan \
  --region us-east-1 \
  --table-name mdip-poc-dev-raw-file-registry
```

### 3B. Preprocessing

What happens:

1. `preprocessor` loads the raw JSON payload
2. removes `segment_id`
3. renders the content to stable Markdown
4. computes `canonicalHash`
5. writes:
   - `processed/{submissionId}/{fileId}.md`

What this proves:

- canonical identity is based on normalized business content, not raw delivery bytes

Important fields:

- `processedS3Key`
- `canonicalHash`
- `businessDocumentKey`
- `sourceUpdatedAt`
- `normalizationStrategy`

Where to inspect:

Processed objects:

```bash
aws s3api list-objects-v2 \
  --region us-east-1 \
  --bucket mdip-poc-dev-docs-ACCOUNT_ID-us-east-1 \
  --prefix "processed/$SUBMISSION_ID/"
```
```
{
    "Contents": [
        {
            "Key": "ingestion/phase14-a-demo01/vertical-farming.json",
            "LastModified": "2026-04-19T04:13:23+00:00",
            "ETag": "\"24055b1f3b07c272152ec1da81f53ac4\"",
            "ChecksumAlgorithm": [
                "CRC32"
            ],
            "ChecksumType": "FULL_OBJECT",
            "Size": 1827671,
            "StorageClass": "STANDARD"
        },
        {
            "Key": "ingestion/phase14-a-demo01/warehouse-robotics.json",
            "LastModified": "2026-04-19T04:13:15+00:00",
            "ETag": "\"fd10e0ae05eda1c6e9a65da49729a3da\"",
            "ChecksumAlgorithm": [
                "CRC32"
            ],
            "ChecksumType": "FULL_OBJECT",
            "Size": 1871832,
            "StorageClass": "STANDARD"
        }
    ],
    "RequestCharged": null,
    "Prefix": "ingestion/phase14-a-demo01/"
}
```
Logs:

- `/aws/lambda/mdip-poc-dev-preprocessor`

Why this matters architecturally:

- it separates transport identity from canonical business identity
- it is the foundation for canonical dedupe and version tracking

### 3C. Canonical Resolution

What happens:

1. `canonical_resolver` looks up `DocumentRegistry` by `canonicalHash`
2. if content already exists, it reuses the existing `documentId`
3. if content is new, it creates a new `documentId`
4. it writes canonical Markdown to:
   - `canonical/{documentId}/...`
5. it records or updates:
   - `DocumentRegistry`

What this proves:

- canonical reuse and document-version creation are explicit behaviors
- the indexable document unit is `documentId`, not raw uploaded file

Important fields:

- `documentId`
- `canonicalHash`
- `canonicalS3Prefix`
- `businessDocumentKey`
- `isActive`
- `kbIngestionStatus`

Where to inspect:

Logs:

- `/aws/lambda/mdip-poc-dev-canonical-resolver`

Document registry:

```bash
aws dynamodb scan \
  --region us-east-1 \
  --table-name mdip-poc-dev-document-registry
```

Why this matters architecturally:

- this is where the design proves that canonical content can be shared across submissions
- it also proves that document lifecycle is a first-class concept, not just a side effect of retrieval

### 3D. Attach Documents To The Submission

What happens:

1. `submission_document_attacher` gathers the file-level canonical results
2. merges `documentId`s onto the submission
3. deduplicates them
4. marks the submission `COMPLETE`

Important fields:

- `SubmissionRegistry.documentIds`
- `SubmissionRegistry.status`

Logs:

- `/aws/lambda/mdip-poc-dev-submission-document-attacher`

Why this matters:

- the submission-to-document relationship is the retrieval boundary used later by the query path
- this is one of the most important state transitions in the whole architecture

## Step 4: Wait For Indexing and Submission Readiness

Command:

```bash
python3 scripts/poll_submission.py "$SUBMISSION_ID" --drive-kb-coordinator
```

What the script does:

- polls `SubmissionRegistry`
- optionally invokes the KB coordinator while waiting
- stops when the submission becomes `READY` or `FAILED`

What happens in the POC:

1. `kb_coordinator` finds documents marked `PENDING_INGESTION`
2. it starts or polls Bedrock ingestion runs
3. `DocumentRegistry.kbIngestionStatus` progresses toward `INDEXED`
4. `submission_readiness_checker` evaluates whether all submission-linked docs are indexed
5. if yes, submission becomes `READY`
6. `ready_callback` marks callback delivery in `SubmissionRegistry`

Relevant components:

- `kb_coordinator` Lambda
- `IngestionRun` DynamoDB table
- Bedrock Knowledge Base
- `submission_readiness_checker` Lambda
- `ready_callback` Lambda

Important document-level fields:

- `kbIngestionStatus`
- `pendingIngestionRunId`
- `lastSuccessfulIngestionRunId`
- `lastIngestionError`

Important submission-level fields:

- `status`
- `readyAt`
- `callbackStatus`
- `callbackDeliveredAt`
- `documentIds`

Expected terminal success state:

- `status = READY`
- `callbackStatus = DELIVERED`
- each linked document has `kbIngestionStatus = INDEXED`

Where to inspect:

Submission registry:

```bash
aws dynamodb get-item \
  --region us-east-1 \
  --table-name mdip-poc-dev-submission-registry \
  --key "{\"submissionId\":{\"S\":\"$SUBMISSION_ID\"}}"
```
```
{
    "Item": {
        "createdAt": {
            "S": "2026-04-19T04:12:21.607547Z"
        },
        "documentIds": {
            "L": []
        },
        "externalRequestId": {
            "S": ""
        },
        "fileIds": {
            "L": [
                {
                    "S": "warehouse-robotics.json"
                },
                {
                    "S": "vertical-farming.json"
                }
            ]
        },
        "ingestionPrefix": {
            "S": "ingestion/phase14-a-demo01/"
        },
        "manifestReceived": {
            "BOOL": false
        },
        "receivedFileCount": {
            "N": "2"
        },
        "status": {
            "S": "RECEIVING"
        },
        "submissionId": {
            "S": "phase14-a-demo01"
        },
        "updatedAt": {
            "S": "2026-04-19T04:12:25.336754Z"
        }
    }
}
```

Document registry:

```bash
aws dynamodb scan \
  --region us-east-1 \
  --table-name mdip-poc-dev-document-registry
```

Ingestion runs:

```bash
aws dynamodb scan \
  --region us-east-1 \
  --table-name mdip-poc-dev-ingestion-run
```

Logs:

- `/aws/lambda/mdip-poc-dev-kb-coordinator`
- `/aws/lambda/mdip-poc-dev-submission-readiness-checker`
- `/aws/lambda/mdip-poc-dev-ready-callback`
- `/aws/bedrock/knowledge-bases/mdip-poc-dev`

Why this matters architecturally:

- it proves the deliberate separation between submission orchestration and Bedrock ingestion coordination
- readiness is derived from document-level index state, not just workflow completion
- the POC demonstrates that “uploaded” and “ready to retrieve” are not the same lifecycle stage

## Step 5: Inspect Canonical Metadata and Stored Content

After the submission is `READY`, inspect the metadata and content that actually back retrieval.

Get the submission:

```bash
aws dynamodb get-item \
  --region us-east-1 \
  --table-name mdip-poc-dev-submission-registry \
  --key "{\"submissionId\":{\"S\":\"$SUBMISSION_ID\"}}"
```

Take the `documentIds` from that output and inspect each:

```bash
aws dynamodb get-item \
  --region us-east-1 \
  --table-name mdip-poc-dev-document-registry \
  --key '{"documentId":{"S":"<DOCUMENT_ID>"}}'
```
```
{
    "Item": {
        "businessDocumentKey": {
            "S": "sample-005"
        },
        "canonicalChunkCount": {
            "N": "194"
        },
        "canonicalHash": {
            "S": "sha256:4fd21f3a6eb695578f9bea7ad7c42c8c0ec0cb1e3c71d49dee2394dcfff31ec0"
        },
        "canonicalS3Prefix": {
            "S": "canonical/doc-4fd21f3a6eb69557/"
        },
        "createdAt": {
            "S": "2026-04-18T21:31:16.904827Z"
        },
        "documentId": {
            "S": "doc-4fd21f3a6eb69557"
        },
        "isActive": {
            "BOOL": false
        },
        "kbIngestionStatus": {
            "S": "INDEXED"
        },
        "lastIngestionError": {
            "NULL": true
        },
        "lastSuccessfulIngestionRunId": {
            "S": "run-87d34ebc-b4e5-4e88-8ddb-60b226ba1172"
        },
        "pendingIngestionRunId": {
            "NULL": true
        },
        "sourceUpdatedAt": {
            "S": "2026-04-17"
        },
        "updatedAt": {
            "S": "2026-04-18T21:41:59.735851Z"
        }
    }
}
```
Inspect canonical objects:

```bash
aws s3api list-objects-v2 \
  --region us-east-1 \
  --bucket mdip-poc-dev-docs-ACCOUNT_ID-us-east-1 \
  --prefix "canonical/<DOCUMENT_ID>/"
```

What to look at:

- `documentId`
- `canonicalHash`
- `businessDocumentKey`
- `sourceUpdatedAt`
- `canonicalChunkCount`
- `isActive`
- `kbIngestionStatus`

Why this matters:

- it shows the true source of indexed content
- it lets you explain the design distinction between:
  - raw upload
  - processed artifact
  - canonical document
  - Bedrock indexed document

## Step 6: Run A Scoped Query

Command:

```bash
python3 scripts/invoke_scoped_query.py "$SUBMISSION_ID" "warehouse robotics"
```
```
{
  "action": "scoped_query_completed",
  "documentIds": [
    "doc-4fd21f3a6eb69557",
    "doc-9cdf074673dafa3b"
  ],
  "modelId": "anthropic.claude-sonnet-4-6",
  "modelInvocationError": null,
  "modelInvocationId": "us.anthropic.claude-sonnet-4-6",
  "modelInvoked": true,
  "queryText": "warehouse robotics",
  "retrievalResultCount": 5,
  "retrievalResults": [
    {
      "contentType": "TEXT",
      "documentId": "doc-4fd21f3a6eb69557",
      "metadata": {
        "documentId": "doc-4fd21f3a6eb69557",
        "x-amz-bedrock-kb-chunk-id": "b5b78d58-2062-4ea1-bb05-3656fa3cb117",
        "x-amz-bedrock-kb-data-source-id": "UY52FI8ALT",
        "x-amz-bedrock-kb-source-file-modality": "TEXT"
      },
      "s3Uri": "s3://mdip-poc-dev-docs-ACCOUNT_ID-us-east-1/canonical/doc-4fd21f3a6eb69557/chunk-0012.md",
      "score": 0.8687129318714142,
      "text": "- A defining feature of Warehouse Robotics and Automation Solutions in the United States is the way management teams balance labor deployment with day-to-day execution. In practice, autonomous mobile robot vendors compete for third-party logistics firms demand through robotics-as-a-service contracts, which creates visible differences in revenue quality and service expectations. This innovation vector narrative is specific to entry 116, where the emphasis falls on product and operating model change and the trade-offs are evaluated against the current operating shape of warehouse robotics. The innovation vector angle in item 116 highlights how field service coverage and local conditions in port-adjacent warehouses alter cost structure, service reliability and the pace of expansion. Margin performance can deteriorate quickly when warehouse downtime sensitivity is treated as temporary rather than structural. Regulatory touchpoints are also relevant because industrial standards groups can influence documentation, reporting cadence and the amount of operational flexibility available to management teams. For that reason, leadership teams track units picked per hour closely and redesign wo"
    },
    {
      "contentType": "TEXT",
      "documentId": "doc-4fd21f3a6eb69557",
      "metadata": {
        "documentId": "doc-4fd21f3a6eb69557",
        "x-amz-bedrock-kb-chunk-id": "ee39be33-3986-4480-8ac1-cd2f2e4cf118",
        "x-amz-bedrock-kb-data-source-id": "UY52FI8ALT",
        "x-amz-bedrock-kb-source-file-modality": "TEXT"
      },
      "s3Uri": "s3://mdip-poc-dev-docs-ACCOUNT_ID-us-east-1/canonical/doc-4fd21f3a6eb69557/chunk-0001.md",
      "score": 0.8669441640377045,
      "text": "Report Id: sample-005\n\nTitle: Warehouse Robotics and Automation Solutions in the United States\n\nIndustry Code: SIM-WRA-005\n\nPublisher Style: Original sample industry report in a commercial market-research style\n\nGeography: United States\n\nReport Date: 2026-04-17\n\nCurrency: USD\n\nExecutive Summary:\n  - Warehouse robotics providers supply hardware, software and integration services that improve throughput, accuracy and labor productivity across fulfillment networks. Demand has been supported by e-commerce growth, labor scarcity, higher service expectations and the need for flexible warehouse capacity. The market has matured from a narrow focus on fixed automation toward a broader portfolio of mobile, modular and software-orchestrated solutions that can be deployed with less facility disruption.\n\n- Customers are no longer buying automation simply to reduce headcount. They are using robotics to stabilize operations, improve order accuracy, support peak demand and reduce dependence on hard-to-staff roles. This has broadened the customer base to include third-party logistics providers, mid-market distributors and specialty manufacturers in addition to large retailers.\n\nIndustry Definition:"
    },
    {
      "contentType": "TEXT",
      "documentId": "doc-4fd21f3a6eb69557",
      "metadata": {
        "documentId": "doc-4fd21f3a6eb69557",
        "x-amz-bedrock-kb-chunk-id": "86d5fa86-619e-4c47-ab9e-41a7f38d7e00",
        "x-amz-bedrock-kb-data-source-id": "UY52FI8ALT",
        "x-amz-bedrock-kb-source-file-modality": "TEXT"
      },
      "s3Uri": "s3://mdip-poc-dev-docs-ACCOUNT_ID-us-east-1/canonical/doc-4fd21f3a6eb69557/chunk-0104.md",
      "score": 0.8568925559520721,
      "text": "Procurement Style: The commercial profile of Warehouse Robotics and Automation Solutions in the United States becomes clearer when the market is examined through pricing architecture. Winning operators tend to match third-party logistics firms needs with robotics-as-a-service contracts, while weaker participants overextend before proving local economics. This persona procurement narrative is specific to entry 572, where the emphasis falls on buying process and account expectations and the trade-offs are evaluated against the current operating shape of warehouse robotics. The persona procurement angle in item 572 highlights how field service coverage and local conditions in port-adjacent warehouses alter cost structure, service reliability and the pace of expansion. The operating model also has to absorb warehouse downtime sensitivity, so revenue growth does not automatically translate into better cash generation. Regulatory touchpoints are also relevant because industrial standards groups can influence documentation, reporting cadence and the amount of operational flexibility available to management teams. This is why units picked per hour remains one of the most useful indicators "
    },
    {
      "contentType": "TEXT",
      "documentId": "doc-4fd21f3a6eb69557",
      "metadata": {
        "documentId": "doc-4fd21f3a6eb69557",
        "x-amz-bedrock-kb-chunk-id": "88ddf254-7de7-401a-878d-2cad346478be",
        "x-amz-bedrock-kb-data-source-id": "UY52FI8ALT",
        "x-amz-bedrock-kb-source-file-modality": "TEXT"
      },
      "s3Uri": "s3://mdip-poc-dev-docs-ACCOUNT_ID-us-east-1/canonical/doc-4fd21f3a6eb69557/chunk-0108.md",
      "score": 0.8559814095497131,
      "text": "Usage Note: The commercial profile of Warehouse Robotics and Automation Solutions in the United States becomes clearer when the market is examined through customer retention. The most stable performers are often the autonomous mobile robot vendors that tailor robotics-as-a-service contracts around the needs of third-party logistics firms segments instead of chasing broad volume. This glossary usage narrative is specific to entry 652, where the emphasis falls on interpretation in diligence and operations and the trade-offs are evaluated against the current operating shape of warehouse robotics. The glossary usage angle in item 652 highlights how field service coverage and local conditions in port-adjacent warehouses alter cost structure, service reliability and the pace of expansion. The operating model also has to absorb warehouse downtime sensitivity, so revenue growth does not automatically translate into better cash generation. Regulatory touchpoints are also relevant because industrial standards groups can influence documentation, reporting cadence and the amount of operational flexibility available to management teams. This is why units picked per hour remains one of the most "
    },
    {
      "contentType": "TEXT",
      "documentId": "doc-4fd21f3a6eb69557",
      "metadata": {
        "documentId": "doc-4fd21f3a6eb69557",
        "x-amz-bedrock-kb-chunk-id": "11591dbe-ae92-45fb-a9f5-72c6c0175ec4",
        "x-amz-bedrock-kb-data-source-id": "UY52FI8ALT",
        "x-amz-bedrock-kb-source-file-modality": "TEXT"
      },
      "s3Uri": "s3://mdip-poc-dev-docs-ACCOUNT_ID-us-east-1/canonical/doc-4fd21f3a6eb69557/chunk-0078.md",
      "score": 0.8558962345123291,
      "text": "Operator Implications: Within Warehouse Robotics and Automation Solutions in the United States, decisions around demand formation now shape both resilience and valuation. Commercial outcomes are closely tied to how fulfillment orchestration providers use systems integrator partnerships to reach retail distribution centers groups that value reliability over novelty. This operator implications narrative is specific to entry 359, where the emphasis falls on required management response and the trade-offs are evaluated against the current operating shape of warehouse robotics. The operator implications angle in item 359 highlights how software talent and local conditions in inland logistics hubs alter cost structure, service reliability and the pace of expansion. That opportunity is offset by pressure from capital budgeting scrutiny, which can narrow margins even when top-line demand appears healthy. Regulatory touchpoints are also relevant because equipment certification bodies can influence documentation, reporting cadence and the amount of operational flexibility available to management teams. As a result, order accuracy often becomes the metric that lenders, boards and commercial p"
    }
  ],
  "retrievedDocumentIds": [
    "doc-4fd21f3a6eb69557"
  ],
  "submissionId": "phase14-a-demo01",
  "submissionStatus": "READY",
  "summaryText": "## Warehouse Robotics \u2013 Summary\n\nBased on the retrieved snippets, here is what is reported about warehouse robotics in the United States:\n\n**Market Overview**\nWarehouse robotics providers supply **hardware, software, and integration services** designed to improve throughput, accuracy, and labor productivity across fulfillment networks. The market has evolved from fixed automation toward **mobile, modular, and software-orchestrated solutions** that can be deployed with less facility disruption.\n\n**Key Demand Drivers**\n- E-commerce growth\n- Labor scarcity\n- Higher service-level expectations\n- Need for flexible warehouse capacity\n\n**Customer Base**\nCustomers have broadened beyond large retailers to include **third-party logistics (3PL) providers, mid-market distributors, and specialty manufacturers**. The buying motivation has shifted from pure headcount reduction to **stabilizing operations, improving order accuracy, and supporting peak demand**.\n\n**Commercial & Operating Model**\n- **Robotics-as-a-service (RaaS)** contracts are a prominent model, with autonomous mobile robot (AMR) vendors competing for 3PL business on this basis.\n- **Field service coverage** and local conditions (e.g., port-adjacent warehouses) materially affect cost structure and service reliability.\n- **Warehouse downtime sensitivity** is a structural risk \u2014 revenue growth does not automatically translate into better cash generation.\n- **Units picked per hour** is a key operational performance metric tracked by leadership teams.\n- Industrial standards groups influence documentation, reporting cadence, and operational flexibility."
}
```
What the script does:

- invokes the `query_api` Lambda directly

What happens in the POC:

1. `query_api` loads the submission from `SubmissionRegistry`
2. reads `documentIds`
3. builds a Bedrock retrieval filter limited to those `documentId`s
4. retrieves only matching chunks from the Knowledge Base
5. invokes Sonnet with only those retrieved snippets
6. returns:
   - retrieval evidence
   - `retrievedDocumentIds`
   - `summaryText`
   - model invocation status

Important response fields:

- `submissionId`
- `documentIds`
- `retrievalResultCount`
- `retrievedDocumentIds`
- `retrievalResults`
- `summaryText`
- `modelInvoked`
- `modelInvocationError`

What success looks like:

- `modelInvoked = true`
- `modelInvocationError = null`
- `retrievedDocumentIds` are only from the submission
- the answer is grounded in scoped retrieved content

Where to inspect:

Direct script output is the best place to inspect `summaryText`.

Logs:

- `/aws/lambda/mdip-poc-dev-query-api`

Important architecture point:

- the query layer is intentionally scoped by `documentId` before the model sees any content
- this is one of the core correctness properties of the whole POC

## Suggested Live Demo Narrative

If you are walking someone through the system, the clearest sequence is:

1. show the manifest
2. upload files and show the S3 ingestion keys
3. show `SubmissionRegistry` in `RECEIVING`
4. trigger completion and show the Step Functions execution
5. explain raw dedupe vs canonical dedupe vs document versioning
6. poll until `READY`
7. inspect `documentIds` and `DocumentRegistry`
8. run the scoped query and show the answer plus the retrieved document IDs

That sequence mirrors the architecture well and makes the important design choices visible rather than abstract.

## Minimal Command List

```bash
export RUN_ID=demo01
export MANIFEST=sample/submissions/submission_a.json
export SUBMISSION_ID=phase14-a-$RUN_ID

sed -n '1,200p' "$MANIFEST"
python3 scripts/upload_test_submission.py "$MANIFEST" --run-id "$RUN_ID"
python3 scripts/trigger_completion.py "$MANIFEST" --run-id "$RUN_ID"
python3 scripts/poll_submission.py "$SUBMISSION_ID" --drive-kb-coordinator
python3 scripts/invoke_scoped_query.py "$SUBMISSION_ID" "warehouse robotics"
```

## Key Demo Takeaways

By the end of this demo, the POC should have visibly proven:

- submissions are explicit multi-file units
- file arrival and submission completion are separate concerns
- raw-file dedupe and canonical dedupe are separate concerns
- canonical documents are the unit of indexing and retrieval
- readiness depends on indexing completion, not upload completion
- retrieval is scoped to a submission’s own `documentId` set before model invocation
