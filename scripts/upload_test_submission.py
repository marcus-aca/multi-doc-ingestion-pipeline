#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from mdip_phase14_lib import create_context, load_manifest, upload_submission


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload one manifest-defined test submission into the ingestion bucket.")
    parser.add_argument("manifest", help="Path to a manifest JSON file under sample/submissions/.")
    parser.add_argument("--run-id", help="Run id used to render submissionIdTemplate manifests.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_manifest(args.manifest, run_id=args.run_id)
    context = create_context()
    result = upload_submission(context, manifest)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

