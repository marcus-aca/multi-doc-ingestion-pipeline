import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
TABLE_NAME = os.environ["SUBMISSION_REGISTRY_TABLE"]
INGESTION_PREFIX = os.environ.get("INGESTION_PREFIX", "ingestion/")


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, int]:
    processed = 0
    ignored = 0

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        event_name = record.get("eventName", "")
        sequencer = record["s3"]["object"].get("sequencer", "")

        if not key.startswith(INGESTION_PREFIX):
            log_info(
                action="ignore_non_ingestion_key",
                bucket=bucket,
                key=key,
                eventName=event_name,
                sequencer=sequencer,
            )
            ignored += 1
            continue

        submission_id, file_id = parse_submission_and_file_id(key)
        upsert_submission(
            submission_id=submission_id,
            file_id=file_id,
            bucket=bucket,
            key=key,
            event_name=event_name,
            sequencer=sequencer,
        )
        processed += 1

    result = {"processed": processed, "ignored": ignored}
    log_info(action="upload_event_handler_result", **result)
    return result


def parse_submission_and_file_id(key: str) -> tuple[str, str]:
    relative_key = key[len(INGESTION_PREFIX) :]
    parts = relative_key.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Unexpected ingestion key format: {key}")

    return parts[0], parts[1]


def upsert_submission(
    submission_id: str,
    file_id: str,
    bucket: str,
    key: str,
    event_name: str,
    sequencer: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"submissionId": {"S": submission_id}},
            UpdateExpression=(
                "SET #status = if_not_exists(#status, :receiving), "
                "#externalRequestId = if_not_exists(#externalRequestId, :empty_string), "
                "#manifestReceived = if_not_exists(#manifestReceived, :false_value), "
                "#ingestionPrefix = if_not_exists(#ingestionPrefix, :ingestion_prefix), "
                "#fileIds = list_append(if_not_exists(#fileIds, :empty_list), :new_file_id), "
                "#documentIds = if_not_exists(#documentIds, :empty_list), "
                "#updatedAt = :now, "
                "#createdAt = if_not_exists(#createdAt, :now) "
                "ADD #receivedFileCount :one"
            ),
            ConditionExpression="attribute_not_exists(#fileIds) OR NOT contains(#fileIds, :file_id_value)",
            ExpressionAttributeNames={
                "#status": "status",
                "#externalRequestId": "externalRequestId",
                "#manifestReceived": "manifestReceived",
                "#ingestionPrefix": "ingestionPrefix",
                "#fileIds": "fileIds",
                "#documentIds": "documentIds",
                "#createdAt": "createdAt",
                "#updatedAt": "updatedAt",
                "#receivedFileCount": "receivedFileCount",
            },
            ExpressionAttributeValues={
                ":receiving": {"S": "RECEIVING"},
                ":empty_string": {"S": ""},
                ":false_value": {"BOOL": False},
                ":ingestion_prefix": {"S": f"{INGESTION_PREFIX}{submission_id}/"},
                ":empty_list": {"L": []},
                ":new_file_id": {"L": [{"S": file_id}]},
                ":file_id_value": {"S": file_id},
                ":now": {"S": now},
                ":one": {"N": "1"},
            },
        )
        log_info(
            action="recorded_submission_file",
            submissionId=submission_id,
            fileId=file_id,
            bucket=bucket,
            key=key,
            eventName=event_name,
            sequencer=sequencer,
            status="RECEIVING",
            receivedFileCountDelta=1,
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        log_info(
            action="ignored_duplicate_submission_file",
            submissionId=submission_id,
            fileId=file_id,
            bucket=bucket,
            key=key,
            eventName=event_name,
            sequencer=sequencer,
        )


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
