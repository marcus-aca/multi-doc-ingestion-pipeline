#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from mdip_phase14_lib import create_context, invoke_scoped_query


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoke the Phase 13 scoped-query Lambda for one submission.")
    parser.add_argument("submission_id", help="Submission id to query.")
    parser.add_argument("query_text", help="Natural-language query text.")
    parser.add_argument("--max-results", type=int, default=5, help="Maximum retrieval results to request.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = create_context()
    result = invoke_scoped_query(
        context,
        submission_id=args.submission_id,
        query_text=args.query_text,
        max_results=args.max_results,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

