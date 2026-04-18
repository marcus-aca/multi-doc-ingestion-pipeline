# Ops Monitor Lambda

This Lambda provides the Phase 15 operational hardening monitor for the POC.

Responsibilities:

- scan pipeline state from DynamoDB
- publish CloudWatch custom metrics for:
  - submissions by status
  - ingestion runs by status
  - callback failures
  - stale submissions
  - stuck `INGESTING` documents
- enqueue manual-review items into SQS when stale or failed pipeline state is detected

The monitor is designed for operational visibility rather than request-path work, so it runs on an EventBridge schedule.
