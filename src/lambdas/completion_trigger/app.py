import json
import logging
import os
from typing import Any

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

stepfunctions = boto3.client("stepfunctions")
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, str]:
    submission_id = event["submissionId"]
    expected_file_ids = event["expectedFileIds"]

    log_info(
        action="start_submission_execution_requested",
        submissionId=submission_id,
        expectedFileIds=expected_file_ids,
        expectedFileCount=len(expected_file_ids),
        stateMachineArn=STATE_MACHINE_ARN,
    )

    response = stepfunctions.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps(
            {
                "submissionId": submission_id,
                "expectedFileIds": expected_file_ids,
                "expectedFileCount": len(expected_file_ids),
            }
        ),
    )

    result = {
        "submissionId": submission_id,
        "executionArn": response["executionArn"],
        "startDate": response["startDate"].isoformat(),
    }
    log_info(action="start_submission_execution_succeeded", **result)
    return result


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
