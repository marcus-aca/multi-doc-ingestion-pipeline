import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")

DOCUMENT_BUCKET_NAME = os.environ["DOCUMENT_BUCKET_NAME"]
RAW_FILE_REGISTRY_TABLE = os.environ["RAW_FILE_REGISTRY_TABLE"]
INGESTION_PREFIX = os.environ.get("INGESTION_PREFIX", "ingestion/")


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    file_id = event["fileId"]

    key = f"{INGESTION_PREFIX}{submission_id}/{file_id}"
    raw_bytes = read_raw_file(key)
    raw_file_hash = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"

    log_info(
        action="raw_file_hash_computed",
        submissionId=submission_id,
        fileId=file_id,
        bucket=DOCUMENT_BUCKET_NAME,
        key=key,
        rawFileHash=raw_file_hash,
    )

    result = claim_or_reuse_raw_file(
        submission_id=submission_id,
        file_id=file_id,
        key=key,
        raw_file_hash=raw_file_hash,
    )
    log_info(**result)
    return result


def read_raw_file(key: str) -> bytes:
    response = s3.get_object(Bucket=DOCUMENT_BUCKET_NAME, Key=key)
    return response["Body"].read()


def claim_or_reuse_raw_file(
    submission_id: str,
    file_id: str,
    key: str,
    raw_file_hash: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        dynamodb.put_item(
            TableName=RAW_FILE_REGISTRY_TABLE,
            Item={
                "rawFileHash": {"S": raw_file_hash},
                "status": {"S": "PROCESSING"},
                "processedS3Key": {"S": ""},
                "canonicalHash": {"S": ""},
                "documentId": {"S": ""},
                "firstSeenAt": {"S": now},
                "lastSeenAt": {"S": now},
                "updatedAt": {"S": now},
            },
            ConditionExpression="attribute_not_exists(rawFileHash)",
        )

        return {
            "action": "raw_file_claimed",
            "submissionId": submission_id,
            "fileId": file_id,
            "bucket": DOCUMENT_BUCKET_NAME,
            "key": key,
            "rawFileHash": raw_file_hash,
            "rawFileStatus": "PROCESSING",
            "ownershipClaimed": True,
            "reusedExistingDocument": False,
            "documentId": None,
        }
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise

    existing_item = dynamodb.get_item(
        TableName=RAW_FILE_REGISTRY_TABLE,
        Key={"rawFileHash": {"S": raw_file_hash}},
        ConsistentRead=True,
    ).get("Item", {})

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    dynamodb.update_item(
        TableName=RAW_FILE_REGISTRY_TABLE,
        Key={"rawFileHash": {"S": raw_file_hash}},
        UpdateExpression="SET #lastSeenAt = :last_seen, #updatedAt = :updated_at",
        ExpressionAttributeNames={
            "#lastSeenAt": "lastSeenAt",
            "#updatedAt": "updatedAt",
        },
        ExpressionAttributeValues={
            ":last_seen": {"S": now},
            ":updated_at": {"S": now},
        },
    )

    existing_status = existing_item.get("status", {}).get("S", "UNKNOWN")
    existing_document_id = existing_item.get("documentId", {}).get("S", "") or None
    existing_canonical_hash = existing_item.get("canonicalHash", {}).get("S", "") or None

    return {
        "action": "raw_file_reused" if existing_status == "RESOLVED" else "raw_file_in_progress",
        "submissionId": submission_id,
        "fileId": file_id,
        "bucket": DOCUMENT_BUCKET_NAME,
        "key": key,
        "rawFileHash": raw_file_hash,
        "rawFileStatus": existing_status,
        "ownershipClaimed": False,
        "reusedExistingDocument": existing_status == "RESOLVED" and existing_document_id is not None,
        "documentId": existing_document_id,
        "canonicalHash": existing_canonical_hash,
    }


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
