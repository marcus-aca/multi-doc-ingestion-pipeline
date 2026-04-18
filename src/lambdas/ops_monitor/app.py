import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
cloudwatch = boto3.client("cloudwatch")
sqs = boto3.client("sqs")
deserializer = TypeDeserializer()

SUBMISSION_REGISTRY_TABLE = os.environ["SUBMISSION_REGISTRY_TABLE"]
DOCUMENT_REGISTRY_TABLE = os.environ["DOCUMENT_REGISTRY_TABLE"]
INGESTION_RUN_TABLE = os.environ["INGESTION_RUN_TABLE"]
MANUAL_REVIEW_QUEUE_URL = os.environ.get("MANUAL_REVIEW_QUEUE_URL", "")
OPERATIONS_METRIC_NAMESPACE = os.environ.get("OPERATIONS_METRIC_NAMESPACE", "MDIP/Operations")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
STALE_INGESTING_THRESHOLD_MINUTES = int(os.environ.get("STALE_INGESTING_THRESHOLD_MINUTES", "15"))
STALE_SUBMISSION_THRESHOLD_MINUTES = int(os.environ.get("STALE_SUBMISSION_THRESHOLD_MINUTES", "15"))

NON_TERMINAL_SUBMISSION_STATUSES = {"RECEIVING", "COMPLETE", "WAITING_FOR_INDEX"}


def lambda_handler(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    submissions = scan_table(SUBMISSION_REGISTRY_TABLE)
    documents = scan_table(DOCUMENT_REGISTRY_TABLE)
    ingestion_runs = scan_table(INGESTION_RUN_TABLE)

    submission_counts = count_by_status(submissions, "status")
    ingestion_run_counts = count_by_status(ingestion_runs, "status")

    stale_submissions = [
        submission
        for submission in submissions
        if submission.get("status") in NON_TERMINAL_SUBMISSION_STATUSES
        and minutes_since(submission.get("updatedAt"), now) >= STALE_SUBMISSION_THRESHOLD_MINUTES
    ]
    stuck_documents = [
        document
        for document in documents
        if document.get("kbIngestionStatus") == "INGESTING"
        and minutes_since(document.get("updatedAt"), now) >= STALE_INGESTING_THRESHOLD_MINUTES
    ]
    callback_failures = [
        submission
        for submission in submissions
        if submission.get("callbackStatus") == "FAILED"
    ]

    manual_review_items = []
    manual_review_items.extend(
        {
            "alertType": "submission_stuck_non_terminal",
            "submissionId": submission.get("submissionId"),
            "status": submission.get("status"),
            "updatedAt": submission.get("updatedAt"),
            "documentIds": submission.get("documentIds", []),
        }
        for submission in stale_submissions
    )
    manual_review_items.extend(
        {
            "alertType": "document_stuck_ingesting",
            "documentId": document.get("documentId"),
            "kbIngestionStatus": document.get("kbIngestionStatus"),
            "pendingIngestionRunId": document.get("pendingIngestionRunId"),
            "updatedAt": document.get("updatedAt"),
            "canonicalHash": document.get("canonicalHash"),
        }
        for document in stuck_documents
    )
    manual_review_items.extend(
        {
            "alertType": "callback_failed",
            "submissionId": submission.get("submissionId"),
            "callbackStatus": submission.get("callbackStatus"),
            "callbackFailureReason": submission.get("callbackFailureReason"),
            "updatedAt": submission.get("updatedAt"),
            "documentIds": submission.get("documentIds", []),
        }
        for submission in callback_failures
    )

    queued_count = 0
    for item in manual_review_items:
        if enqueue_manual_review(item):
            queued_count += 1

    put_metrics(submission_counts, ingestion_run_counts, len(stuck_documents), len(stale_submissions), len(callback_failures), queued_count)

    result = {
        "action": "ops_monitor_completed",
        "environment": ENVIRONMENT,
        "submissionCounts": submission_counts,
        "ingestionRunCounts": ingestion_run_counts,
        "documentsStuckInIngesting": len(stuck_documents),
        "submissionsStuckNonTerminal": len(stale_submissions),
        "callbackFailures": len(callback_failures),
        "manualReviewItemsQueued": queued_count,
    }
    log_info(**result)
    return result


def scan_table(table_name: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    exclusive_start_key: dict[str, Any] | None = None

    while True:
        scan_kwargs: dict[str, Any] = {"TableName": table_name}
        if exclusive_start_key is not None:
            scan_kwargs["ExclusiveStartKey"] = exclusive_start_key
        response = dynamodb.scan(**scan_kwargs)
        items.extend(deserialize_item(item) for item in response.get("Items", []))
        exclusive_start_key = response.get("LastEvaluatedKey")
        if exclusive_start_key is None:
            break

    return items


def count_by_status(items: list[dict[str, Any]], status_key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get(status_key, "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def put_metrics(
    submission_counts: dict[str, int],
    ingestion_run_counts: dict[str, int],
    stuck_documents_count: int,
    stale_submissions_count: int,
    callback_failure_count: int,
    manual_review_items_queued: int,
) -> None:
    metric_data: list[dict[str, Any]] = []

    for status, count in submission_counts.items():
        metric_data.append(
            build_metric("SubmissionCount", count, dimensions=[{"Name": "Environment", "Value": ENVIRONMENT}, {"Name": "Status", "Value": status}])
        )

    for status, count in ingestion_run_counts.items():
        metric_data.append(
            build_metric("IngestionRunCount", count, dimensions=[{"Name": "Environment", "Value": ENVIRONMENT}, {"Name": "Status", "Value": status}])
        )

    metric_data.extend(
        [
            build_metric("DocumentsStuckInIngesting", stuck_documents_count),
            build_metric("SubmissionsStuckNonTerminal", stale_submissions_count),
            build_metric("CallbackFailureCount", callback_failure_count),
            build_metric("ManualReviewItemsQueued", manual_review_items_queued),
        ]
    )

    for start in range(0, len(metric_data), 20):
        cloudwatch.put_metric_data(
            Namespace=OPERATIONS_METRIC_NAMESPACE,
            MetricData=metric_data[start:start + 20],
        )


def build_metric(metric_name: str, value: int, dimensions: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "MetricName": metric_name,
        "Dimensions": dimensions or [{"Name": "Environment", "Value": ENVIRONMENT}],
        "Timestamp": datetime.now(timezone.utc),
        "Value": value,
        "Unit": "Count",
    }


def enqueue_manual_review(item: dict[str, Any]) -> bool:
    if MANUAL_REVIEW_QUEUE_URL == "":
        return False

    message = dict(item)
    message["environment"] = ENVIRONMENT
    sqs.send_message(
        QueueUrl=MANUAL_REVIEW_QUEUE_URL,
        MessageBody=json.dumps(message, sort_keys=True, default=str),
        MessageGroupId=message["alertType"],
    )
    log_info(action="ops_monitor_manual_review_enqueued", **message)
    return True


def minutes_since(timestamp: str | None, now: datetime) -> float:
    if not timestamp:
        return 0
    parsed = parse_utc_timestamp(timestamp)
    return (now - parsed).total_seconds() / 60.0


def parse_utc_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: convert_decimals(deserializer.deserialize(value)) for key, value in item.items()}


def convert_decimals(value: Any) -> Any:
    if isinstance(value, list):
        return [convert_decimals(item) for item in value]
    if isinstance(value, dict):
        return {key: convert_decimals(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True, default=str))
