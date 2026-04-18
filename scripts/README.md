# Phase 14 Scripts

These scripts provide the operator tooling called for by Phase 14.

Usage examples:

```bash
python3 scripts/upload_test_submission.py sample/submissions/submission_a.json --run-id demo01
python3 scripts/trigger_completion.py sample/submissions/submission_a.json --run-id demo01
python3 scripts/poll_submission.py phase14-a-demo01 --drive-kb-coordinator
python3 scripts/invoke_scoped_query.py phase14-a-demo01 "warehouse robotics"
python3 scripts/validate_phase14.py --drive-kb-coordinator
python3 scripts/validate_phase16.py --run-id demo-exit --drive-kb-coordinator
python3 scripts/validate_phase16.py --run-id demo-fresh --drive-kb-coordinator --validated-fresh-create
```

Manifest notes:

- `submissionIdTemplate` lets one manifest be reused across many validation runs.
- `verbatim` preserves the exact source bytes.
- `compact_json` rewrites the same JSON content into minified bytes to force canonical reuse without raw-byte reuse.
- `update_top_level_fields` creates a newer business-document version while keeping the same `report_id`.
