import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
deserializer = TypeDeserializer()

SUBMISSION_REGISTRY_TABLE = os.environ["SUBMISSION_REGISTRY_TABLE"]


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    raw_file_results = event.get("rawFileResults", [])

    resolved_document_ids = extract_document_ids(raw_file_results)
    submission_item = get_submission(submission_id)
    existing_document_ids = submission_item.get("documentIds", [])
    merged_document_ids = sorted(set(existing_document_ids) | set(resolved_document_ids))
    now = utc_now()

    dynamodb.update_item(
        TableName=SUBMISSION_REGISTRY_TABLE,
        Key={"submissionId": {"S": submission_id}},
        UpdateExpression="SET #documentIds = :document_ids, #status = :status, #updatedAt = :updated_at",
        ExpressionAttributeNames={
            "#documentIds": "documentIds",
            "#status": "status",
            "#updatedAt": "updatedAt",
        },
        ExpressionAttributeValues={
            ":document_ids": {"L": [{"S": value} for value in merged_document_ids]},
            ":status": {"S": "COMPLETE"},
            ":updated_at": {"S": now},
        },
    )

    result = {
        "action": "submission_documents_attached",
        "submissionId": submission_id,
        "documentIds": merged_document_ids,
        "documentCount": len(merged_document_ids),
        "status": "COMPLETE",
    }
    log_info(**result)
    return result


def extract_document_ids(raw_file_results: list[dict[str, Any]]) -> list[str]:
    document_ids: list[str] = []
    for item in raw_file_results:
        canonical = item.get("canonical") or {}
        resolution = item.get("resolution") or {}
        document_id = canonical.get("documentId") or resolution.get("documentId")
        if document_id:
            document_ids.append(document_id)
    return document_ids


def get_submission(submission_id: str) -> dict[str, Any]:
    response = dynamodb.get_item(
        TableName=SUBMISSION_REGISTRY_TABLE,
        Key={"submissionId": {"S": submission_id}},
        ConsistentRead=True,
    )
    return deserialize_item(response.get("Item", {}))


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserializer.deserialize(value) for key, value in item.items()}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
