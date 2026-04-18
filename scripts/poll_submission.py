#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from mdip_phase14_lib import create_context, wait_for_submission_terminal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll a submission until it becomes READY or FAILED.")
    parser.add_argument("submission_id", help="Submission id to poll.")
    parser.add_argument("--execution-arn", help="Optional Step Functions execution ARN to track alongside the submission.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="How long to wait before failing.")
    parser.add_argument("--poll-seconds", type=int, default=10, help="Polling interval in seconds.")
    parser.add_argument(
        "--drive-kb-coordinator",
        action="store_true",
        help="Invoke the KB coordinator during polling to avoid waiting for the EventBridge schedule.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = create_context()
    result = wait_for_submission_terminal(
        ctx=context,
        submission_id=args.submission_id,
        execution_arn=args.execution_arn,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        drive_kb_coordinator=args.drive_kb_coordinator,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()

