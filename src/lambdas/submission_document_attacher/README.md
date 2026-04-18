# Submission Document Attacher Lambda

This Lambda finalizes Phase 8 at the submission level.

Responsibilities:

- read document IDs resolved during the Step Functions file map
- merge them onto `SubmissionRegistry.documentIds`
- deduplicate document membership
- mark the submission `COMPLETE`

Expected event shape:

```json
{
  "submissionId": "sub-001",
  "rawFileResults": [
    {
      "canonical": {
        "documentId": "doc-001"
      }
    }
  ]
}
```
