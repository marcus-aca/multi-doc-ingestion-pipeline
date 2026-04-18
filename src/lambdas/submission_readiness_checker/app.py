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
DOCUMENT_REGISTRY_TABLE = os.environ["DOCUMENT_REGISTRY_TABLE"]


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    document_ids = event.get("documentIds") or get_submission(submission_id).get("documentIds", [])
    document_states = load_document_states(document_ids)

    indexed_document_ids = []
    pending_document_ids = []
    failed_document_ids = []

    for document_id, document in document_states.items():
        status = document.get("kbIngestionStatus", "UNKNOWN")
        if status == "INDEXED":
            indexed_document_ids.append(document_id)
        elif status == "FAILED":
            failed_document_ids.append(document_id)
        else:
            pending_document_ids.append(document_id)

    now = utc_now()
    if failed_document_ids:
        update_submission_status(submission_id=submission_id, status="FAILED", now=now, set_ready_at=False)
        result = {
            "action": "submission_readiness_failed",
            "submissionId": submission_id,
            "documentIds": document_ids,
            "indexedDocumentIds": indexed_document_ids,
            "pendingDocumentIds": pending_document_ids,
            "failedDocumentIds": failed_document_ids,
            "documentStates": summarize_document_states(document_states),
            "isReady": False,
            "hasFailures": True,
            "status": "FAILED",
        }
        log_info(**result)
        return result

    if document_ids and not pending_document_ids:
        update_submission_status(submission_id=submission_id, status="READY", now=now, set_ready_at=True)
        result = {
            "action": "submission_ready",
            "submissionId": submission_id,
            "documentIds": document_ids,
            "indexedDocumentIds": indexed_document_ids,
            "pendingDocumentIds": pending_document_ids,
            "failedDocumentIds": failed_document_ids,
            "documentStates": summarize_document_states(document_states),
            "isReady": True,
            "hasFailures": False,
            "status": "READY",
            "readyAt": now,
        }
        log_info(**result)
        return result

    update_submission_status(submission_id=submission_id, status="WAITING_FOR_INDEX", now=now, set_ready_at=False)
    result = {
        "action": "submission_waiting_for_index",
        "submissionId": submission_id,
        "documentIds": document_ids,
        "indexedDocumentIds": indexed_document_ids,
        "pendingDocumentIds": pending_document_ids,
        "failedDocumentIds": failed_document_ids,
        "documentStates": summarize_document_states(document_states),
        "isReady": False,
        "hasFailures": False,
        "status": "WAITING_FOR_INDEX",
    }
    log_info(**result)
    return result


def get_submission(submission_id: str) -> dict[str, Any]:
    response = dynamodb.get_item(
        TableName=SUBMISSION_REGISTRY_TABLE,
        Key={"submissionId": {"S": submission_id}},
        ConsistentRead=True,
    )
    return deserialize_item(response.get("Item", {}))


def load_document_states(document_ids: list[str]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for document_id in document_ids:
        response = dynamodb.get_item(
            TableName=DOCUMENT_REGISTRY_TABLE,
            Key={"documentId": {"S": document_id}},
            ConsistentRead=True,
        )
        states[document_id] = deserialize_item(response.get("Item", {}))
    return states


def update_submission_status(submission_id: str, status: str, now: str, set_ready_at: bool) -> None:
    update_expression = "SET #status = :status, #updatedAt = :updated_at"
    expression_attribute_names = {
        "#status": "status",
        "#updatedAt": "updatedAt",
    }
    expression_attribute_values = {
        ":status": {"S": status},
        ":updated_at": {"S": now},
    }

    if set_ready_at:
        update_expression += ", #readyAt = :ready_at"
        expression_attribute_names["#readyAt"] = "readyAt"
        expression_attribute_values[":ready_at"] = {"S": now}

    dynamodb.update_item(
        TableName=SUBMISSION_REGISTRY_TABLE,
        Key={"submissionId": {"S": submission_id}},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
    )


def summarize_document_states(document_states: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for document_id, document in document_states.items():
        summary.append(
            {
                "documentId": document_id,
                "kbIngestionStatus": document.get("kbIngestionStatus", "MISSING"),
                "pendingIngestionRunId": document.get("pendingIngestionRunId"),
                "lastSuccessfulIngestionRunId": document.get("lastSuccessfulIngestionRunId"),
                "lastIngestionError": document.get("lastIngestionError"),
            }
        )
    return summary


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserializer.deserialize(value) for key, value in item.items()}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
