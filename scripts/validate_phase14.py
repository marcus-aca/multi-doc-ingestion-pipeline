#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from mdip_phase14_lib import (
    create_context,
    get_document,
    get_submission,
    invoke_scoped_query,
    load_manifest,
    materialize_manifest_files,
    query_documents_by_business_key,
    trigger_completion,
    upload_submission,
    utc_run_id,
    wait_for_submission_files,
    wait_for_submission_terminal,
)


DEFAULT_MANIFESTS = [
    "sample/submissions/submission_a.json",
    "sample/submissions/submission_b.json",
    "sample/submissions/submission_c.json",
    "sample/submissions/submission_d.json",
    "sample/submissions/submission_e.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full Phase 14 validation flow for submissions A-E.")
    parser.add_argument("--run-id", help="Optional run id used to render submission ids. Defaults to current UTC timestamp.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="How long to wait for each submission.")
    parser.add_argument("--poll-seconds", type=int, default=10, help="Polling interval while waiting for READY.")
    parser.add_argument(
        "--drive-kb-coordinator",
        action="store_true",
        help="Invoke the KB coordinator during readiness polling so validation does not wait on EventBridge.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id or utc_run_id()
    context = create_context()
    manifests = [load_manifest(path, run_id=run_id) for path in DEFAULT_MANIFESTS]

    summary: dict[str, Any] = {
        "runId": run_id,
        "region": context.region,
        "submissions": {},
        "assertions": {},
    }

    expected_files_by_submission: dict[str, list[dict[str, Any]]] = {}
    for manifest in manifests:
        expected_files_by_submission[manifest["label"]] = materialize_manifest_files(manifest)
        upload_result = upload_submission(context, manifest)
        wait_for_submission_files(
            context,
            submission_id=manifest["submissionId"],
            expected_file_ids=[file_spec["fileId"] for file_spec in manifest["files"]],
            timeout_seconds=60,
        )
        trigger_result = trigger_completion(
            context,
            manifest["submissionId"],
            [file_spec["fileId"] for file_spec in manifest["files"]],
        )
        terminal_result = wait_for_submission_terminal(
            ctx=context,
            submission_id=manifest["submissionId"],
            execution_arn=trigger_result.get("executionArn"),
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            drive_kb_coordinator=args.drive_kb_coordinator,
        )
        submission = terminal_result["submission"]
        if submission.get("status") != "READY":
            raise AssertionError(
                f"Submission {manifest['label']} resolved to {submission.get('status')} instead of READY."
            )
        summary["submissions"][manifest["label"]] = {
            "submissionId": manifest["submissionId"],
            "upload": {
                "uploadedKeys": upload_result["uploadedKeys"],
            },
            "completion": trigger_result,
            "terminal": terminal_result,
        }

    a_submission = get_submission(context, summary["submissions"]["A"]["submissionId"])
    b_submission = get_submission(context, summary["submissions"]["B"]["submissionId"])
    c_submission = get_submission(context, summary["submissions"]["C"]["submissionId"])
    d_submission = get_submission(context, summary["submissions"]["D"]["submissionId"])
    e_submission = get_submission(context, summary["submissions"]["E"]["submissionId"])

    ensure(len(a_submission.get("documentIds", [])) == 2, "Submission A should have two document ids.")
    ensure(len(b_submission.get("documentIds", [])) == 2, "Submission B should have two document ids.")
    ensure(len(c_submission.get("documentIds", [])) == 2, "Submission C should have two document ids.")
    ensure(len(d_submission.get("documentIds", [])) == 2, "Submission D should have two document ids.")
    ensure(len(e_submission.get("documentIds", [])) == 2, "Submission E should have two document ids.")

    exact_raw_match = compare_file_identity(
        expected_files_by_submission["A"][0],
        expected_files_by_submission["C"][0],
    )
    canonical_match = compare_file_identity(
        expected_files_by_submission["A"][0],
        expected_files_by_submission["D"][0],
    )
    updated_business_doc = compare_file_identity(
        expected_files_by_submission["A"][0],
        expected_files_by_submission["E"][0],
    )

    ensure(exact_raw_match["rawFileHashMatches"], "Submission C should reuse the exact raw file from submission A.")
    ensure(exact_raw_match["canonicalHashMatches"], "Submission C should also reuse A's canonical hash.")
    ensure(
        canonical_match["canonicalHashMatches"] and not canonical_match["rawFileHashMatches"],
        "Submission D should reuse A's canonical document with different raw bytes.",
    )
    ensure(
        not updated_business_doc["canonicalHashMatches"],
        "Submission E should produce a new canonical document for the updated business document.",
    )

    reused_exact_document_id = match_document_id_for_canonical_hash(
        context,
        a_submission["documentIds"],
        expected_files_by_submission["A"][0]["canonicalHash"],
    )
    reused_c_document_id = match_document_id_for_canonical_hash(
        context,
        c_submission["documentIds"],
        expected_files_by_submission["C"][0]["canonicalHash"],
    )
    reused_d_document_id = match_document_id_for_canonical_hash(
        context,
        d_submission["documentIds"],
        expected_files_by_submission["D"][0]["canonicalHash"],
    )
    updated_e_document_id = match_document_id_for_canonical_hash(
        context,
        e_submission["documentIds"],
        expected_files_by_submission["E"][0]["canonicalHash"],
    )

    ensure(
        reused_exact_document_id == reused_c_document_id,
        "Submission C should point at the same document id as submission A for the exact raw duplicate.",
    )
    ensure(
        reused_exact_document_id == reused_d_document_id,
        "Submission D should point at the same document id as submission A for the canonical duplicate.",
    )
    ensure(
        reused_exact_document_id != updated_e_document_id,
        "Submission E should create a new document id for the updated business document.",
    )

    previous_doc = get_document(context, reused_exact_document_id)
    updated_doc = get_document(context, updated_e_document_id)
    business_documents = query_documents_by_business_key(context, "sample-005")

    ensure(previous_doc.get("isActive") is False, "The older sample-005 document should no longer be active after E.")
    ensure(updated_doc.get("isActive") is True, "The updated sample-005 document should be active after E.")
    ensure(len(business_documents) >= 2, "Expected at least two versions of businessDocumentKey sample-005.")

    positive_query = invoke_scoped_query(context, a_submission["submissionId"], "autonomous mobile robots")
    negative_query = invoke_scoped_query(context, a_submission["submissionId"], "veterinary expenses")
    b_positive_query = invoke_scoped_query(context, b_submission["submissionId"], "veterinary expenses")

    ensure(
        positive_query["retrievalResultCount"] > 0,
        "Submission A should return scoped results for a query grounded in its own documents.",
    )
    ensure(
        set(negative_query["retrievedDocumentIds"]).issubset(set(a_submission["documentIds"])),
        "Submission A returned a leaked document id for the pet-insurance-oriented query.",
    )
    ensure(
        set(negative_query["retrievedDocumentIds"]).isdisjoint(set(b_submission["documentIds"])),
        "Submission A query leaked a document id from submission B.",
    )
    ensure(
        negative_query["retrievalResultCount"] >= 0,
        "Submission A scoped query should complete successfully.",
    )
    ensure(
        b_positive_query["retrievalResultCount"] > 0,
        "Submission B should return results for a query grounded in its own documents.",
    )
    ensure(
        set(positive_query["retrievedDocumentIds"]).issubset(set(a_submission["documentIds"])),
        "Submission A retrieval returned a document outside the submission scope.",
    )
    ensure(
        set(b_positive_query["retrievedDocumentIds"]).issubset(set(b_submission["documentIds"])),
        "Submission B retrieval returned a document outside the submission scope.",
    )

    summary["assertions"] = {
        "submissionCReusesExactRawDocumentId": reused_exact_document_id == reused_c_document_id,
        "submissionDReusesCanonicalDocumentId": reused_exact_document_id == reused_d_document_id,
        "submissionECreatesNewVersion": reused_exact_document_id != updated_e_document_id,
        "submissionEActivatesLatestBusinessDocument": updated_doc.get("isActive") is True,
        "submissionAQueryIsScoped": set(negative_query["retrievedDocumentIds"]).isdisjoint(set(b_submission["documentIds"])),
        "submissionBQueryReturnsOwnDocuments": b_positive_query["retrievalResultCount"] > 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


def match_document_id_for_canonical_hash(
    context: Any,
    document_ids: list[str],
    canonical_hash: str,
) -> str:
    for document_id in document_ids:
        if get_document(context, document_id).get("canonicalHash") == canonical_hash:
            return document_id
    raise AssertionError(f"Could not find canonical hash {canonical_hash} within document ids {document_ids}.")


def compare_file_identity(left: dict[str, Any], right: dict[str, Any]) -> dict[str, bool]:
    return {
        "rawFileHashMatches": left["rawFileHash"] == right["rawFileHash"],
        "canonicalHashMatches": left["canonicalHash"] == right["canonicalHash"],
    }


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    main()
