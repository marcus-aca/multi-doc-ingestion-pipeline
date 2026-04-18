import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
sqs = boto3.client("sqs")

SUBMISSION_REGISTRY_TABLE = os.environ["SUBMISSION_REGISTRY_TABLE"]
MANUAL_REVIEW_QUEUE_URL = os.environ.get("MANUAL_REVIEW_QUEUE_URL", "")


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    status = event["status"]
    ready_at = event.get("readyAt")
    document_ids = event.get("documentIds", [])
    now = utc_now()

    try:
        if event.get("forceFailure") is True:
            raise RuntimeError("Forced ready callback failure for Phase 15 validation.")

        dynamodb.update_item(
            TableName=SUBMISSION_REGISTRY_TABLE,
            Key={"submissionId": {"S": submission_id}},
            UpdateExpression="SET #callbackStatus = :callback_status, #callbackDeliveredAt = :callback_delivered_at, #updatedAt = :updated_at",
            ExpressionAttributeNames={
                "#callbackStatus": "callbackStatus",
                "#callbackDeliveredAt": "callbackDeliveredAt",
                "#updatedAt": "updatedAt",
            },
            ExpressionAttributeValues={
                ":callback_status": {"S": "DELIVERED"},
                ":callback_delivered_at": {"S": now},
                ":updated_at": {"S": now},
            },
        )

        result = {
            "action": "ready_callback_delivered",
            "submissionId": submission_id,
            "status": status,
            "readyAt": ready_at,
            "documentIds": document_ids,
            "callbackStatus": "DELIVERED",
            "callbackDeliveredAt": now,
            "deliveryMode": "mock_lambda",
        }
        log_info(**result)
        return result
    except Exception as error:
        mark_callback_failed(submission_id=submission_id, now=now, error_message=str(error))
        enqueue_manual_review(
            {
                "alertType": "callback_failed",
                "submissionId": submission_id,
                "status": status,
                "readyAt": ready_at,
                "documentIds": document_ids,
                "callbackFailureReason": str(error),
            }
        )
        log_info(
            action="ready_callback_failed",
            submissionId=submission_id,
            status=status,
            readyAt=ready_at,
            documentIds=document_ids,
            callbackStatus="FAILED",
            callbackFailureReason=str(error),
            errorType=type(error).__name__,
        )
        raise


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def mark_callback_failed(submission_id: str, now: str, error_message: str) -> None:
    dynamodb.update_item(
        TableName=SUBMISSION_REGISTRY_TABLE,
        Key={"submissionId": {"S": submission_id}},
        UpdateExpression="SET #callbackStatus = :callback_status, #callbackFailedAt = :callback_failed_at, #callbackFailureReason = :callback_failure_reason, #updatedAt = :updated_at",
        ExpressionAttributeNames={
            "#callbackStatus": "callbackStatus",
            "#callbackFailedAt": "callbackFailedAt",
            "#callbackFailureReason": "callbackFailureReason",
            "#updatedAt": "updatedAt",
        },
        ExpressionAttributeValues={
            ":callback_status": {"S": "FAILED"},
            ":callback_failed_at": {"S": now},
            ":callback_failure_reason": {"S": error_message[:2048]},
            ":updated_at": {"S": now},
        },
    )


def enqueue_manual_review(message: dict[str, Any]) -> None:
    if MANUAL_REVIEW_QUEUE_URL == "":
        return

    sqs.send_message(
        QueueUrl=MANUAL_REVIEW_QUEUE_URL,
        MessageBody=json.dumps(message, sort_keys=True),
        MessageGroupId=message["alertType"],
    )
    log_info(action="manual_review_enqueued", **message)


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
