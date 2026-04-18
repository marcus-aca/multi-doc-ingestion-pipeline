#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from mdip_phase14_lib import create_context, load_manifest, trigger_completion, wait_for_submission_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoke the completion trigger for a manifest-defined submission.")
    parser.add_argument("manifest", help="Path to a manifest JSON file under sample/submissions/.")
    parser.add_argument("--run-id", help="Run id used to render submissionIdTemplate manifests.")
    parser.add_argument(
        "--wait-for-upload-seconds",
        type=int,
        default=60,
        help="How long to wait for S3 upload events to populate SubmissionRegistry before triggering completion.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_manifest(args.manifest, run_id=args.run_id)
    expected_file_ids = [file_spec["fileId"] for file_spec in manifest["files"]]
    context = create_context()
    wait_for_submission_files(
        context,
        submission_id=manifest["submissionId"],
        expected_file_ids=expected_file_ids,
        timeout_seconds=args.wait_for_upload_seconds,
    )
    result = trigger_completion(context, manifest["submissionId"], expected_file_ids)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
