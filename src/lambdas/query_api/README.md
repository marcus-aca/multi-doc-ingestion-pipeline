# Query API Lambda

This Lambda is the Phase 13 scoped-query entry point for the POC.

Current behavior:

- accepts `submissionId` and `queryText`
- loads the submission from `SubmissionRegistry`
- reads the submission-linked `documentId`s
- calls Bedrock Knowledge Base retrieval with a metadata filter limited to those `documentId`s
- calls Claude Sonnet 4.6 with only the scoped retrieved snippets
- returns both retrieval evidence and a short model response

This keeps the POC retrieval model aligned with the future AgentCore path:

- submission scoping comes from DynamoDB
- KB retrieval is filtered by `documentId`
- Sonnet only sees the scoped retrieved content

For now this Lambda is invoked directly for validation. A later phase can move the same logic behind a fuller AgentCore Runtime entry point.
