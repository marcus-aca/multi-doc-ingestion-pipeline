#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from mdip_phase14_lib import create_context, invoke_scoped_query, load_terraform_outputs, utc_run_id


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 16 exit-checklist validator.")
    parser.add_argument("--run-id", help="Optional run id. Defaults to current UTC timestamp.")
    parser.add_argument("--timeout-seconds", type=int, default=1200, help="Timeout forwarded to Phase 14 validation.")
    parser.add_argument("--poll-seconds", type=int, default=10, help="Polling interval forwarded to Phase 14 validation.")
    parser.add_argument(
        "--drive-kb-coordinator",
        action="store_true",
        help="Invoke the KB coordinator while waiting so validation does not depend on the EventBridge cadence.",
    )
    parser.add_argument(
        "--validated-fresh-create",
        action="store_true",
        help="Mark the Terraform from-scratch checklist item complete for runs executed after a full destroy and recreate.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id or f"phase16-{utc_run_id()}"
    terraform_outputs = load_terraform_outputs()
    phase14_summary = run_phase14_validation(
        run_id=run_id,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        drive_kb_coordinator=args.drive_kb_coordinator,
    )

    context = create_context()
    submission_a_id = phase14_summary["submissions"]["A"]["submissionId"]
    query_result = invoke_scoped_query(context, submission_a_id, "autonomous mobile robots")

    checklist = {
        "terraform_create_from_scratch": {
            "status": "complete" if args.validated_fresh_create else "not_validated",
            "reason": (
                "Validated by running this checklist after a full Terraform destroy and recreate."
                if args.validated_fresh_create
                else "Current Phase 16 validation did not destroy and recreate the environment from scratch."
            ),
        },
        "manual_test_submission_completes_successfully": {
            "status": "complete",
            "evidence": phase14_summary["submissions"]["A"]["terminal"],
        },
        "duplicate_raw_file_reused_correctly": {
            "status": "complete" if phase14_summary["assertions"]["submissionCReusesExactRawDocumentId"] else "failed",
        },
        "canonical_duplicate_reused_correctly": {
            "status": "complete" if phase14_summary["assertions"]["submissionDReusesCanonicalDocumentId"] else "failed",
        },
        "business_document_update_becomes_active_correctly": {
            "status": "complete" if phase14_summary["assertions"]["submissionEActivatesLatestBusinessDocument"] else "failed",
        },
        "knowledge_base_ingestion_run_indexes_changed_docs": {
            "status": "complete",
            "reason": "All Phase 14 validation submissions finished READY after indexing completed.",
        },
        "scoped_retrieval_proves_submission_isolation": {
            "status": "complete" if phase14_summary["assertions"]["submissionAQueryIsScoped"] else "failed",
            "reason": "Validated through the current scoped-query Lambda wrapper that matches the future AgentCore scoping model.",
        },
        "sonnet_invocation_works_with_only_scoped_retrieval_results": {
            "status": "complete" if query_result.get("modelInvoked") and not query_result.get("modelInvocationError") else "blocked",
            "reason": query_result.get("modelInvocationError") or "Model invocation succeeded.",
        },
        "team_walkthrough_completed_and_open_issues_captured": {
            "status": "not_validated",
            "reason": "This is a team/process item and was not performed by the automated validator.",
        },
    }

    report = {
        "runId": run_id,
        "region": terraform_outputs["aws_region"],
        "resourceOutputs": {
            "documentBucketName": terraform_outputs["document_bucket_name"],
            "knowledgeBaseId": terraform_outputs["knowledge_base_id"],
            "manualReviewQueueUrl": terraform_outputs.get("manual_review_queue_url"),
            "operationsDashboardName": terraform_outputs.get("operations_dashboard_name"),
        },
        "phase14Summary": phase14_summary,
        "scopedQueryCheck": {
            "submissionId": submission_a_id,
            "modelInvoked": query_result.get("modelInvoked"),
            "modelInvocationError": query_result.get("modelInvocationError"),
            "retrievalResultCount": query_result.get("retrievalResultCount"),
            "retrievedDocumentIds": query_result.get("retrievedDocumentIds"),
        },
        "checklist": checklist,
    }
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


def run_phase14_validation(
    run_id: str,
    timeout_seconds: int,
    poll_seconds: int,
    drive_kb_coordinator: bool,
) -> dict[str, Any]:
    command = [
        "python3",
        "scripts/validate_phase14.py",
        "--run-id",
        run_id,
        "--timeout-seconds",
        str(timeout_seconds),
        "--poll-seconds",
        str(poll_seconds),
    ]
    if drive_kb_coordinator:
        command.append("--drive-kb-coordinator")

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Phase 14 validation failed while running Phase 16 validation.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return json.loads(result.stdout)


if __name__ == "__main__":
    main()
