import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")
deserializer = TypeDeserializer()

DOCUMENT_BUCKET_NAME = os.environ["DOCUMENT_BUCKET_NAME"]
RAW_FILE_REGISTRY_TABLE = os.environ["RAW_FILE_REGISTRY_TABLE"]
DOCUMENT_REGISTRY_TABLE = os.environ["DOCUMENT_REGISTRY_TABLE"]
CANONICAL_PREFIX = os.environ.get("CANONICAL_PREFIX", "canonical/")
CANONICAL_CHUNK_MAX_CHARS = int(os.environ.get("CANONICAL_CHUNK_MAX_CHARS", "4000"))


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    file_id = event["fileId"]
    raw_file_hash = event["rawFileHash"]
    processed_s3_key = event["processedS3Key"]
    canonical_hash = event["canonicalHash"]
    business_document_key = normalize_optional_string(event.get("businessDocumentKey"))
    source_version = normalize_optional_string(event.get("sourceVersion"))
    source_updated_at = normalize_optional_string(event.get("sourceUpdatedAt"))
    canonical_text = read_text_from_s3(processed_s3_key)

    document_id = build_document_id(canonical_hash)
    canonical_s3_prefix = f"{CANONICAL_PREFIX}{document_id}/"
    now = utc_now()

    existing_document = find_document_by_canonical_hash(canonical_hash)
    if existing_document is None:
        chunk_records = build_canonical_chunk_records(
            document_id=document_id,
            canonical_s3_prefix=canonical_s3_prefix,
            canonical_text=canonical_text,
        )
        create_canonical_document(
            document_id=document_id,
            canonical_hash=canonical_hash,
            canonical_s3_prefix=canonical_s3_prefix,
            chunk_records=chunk_records,
            business_document_key=business_document_key,
            source_version=source_version,
            source_updated_at=source_updated_at,
            now=now,
        )
        canonical_chunk_count = len(chunk_records)
        reused_existing_document = False
    else:
        document_id = existing_document["documentId"]
        canonical_s3_prefix = existing_document["canonicalS3Prefix"]
        canonical_chunk_count = int(existing_document.get("canonicalChunkCount", 0))
        if is_compatible_business_key(existing_document=existing_document, business_document_key=business_document_key):
            update_existing_document_metadata(
                document_id=document_id,
                business_document_key=business_document_key,
                source_version=source_version,
                source_updated_at=source_updated_at,
                now=now,
            )
        reused_existing_document = True

    activation_result = determine_active_document(
        document_id=document_id,
        business_document_key=business_document_key,
        source_version=source_version,
        source_updated_at=source_updated_at,
        now=now,
    )

    resolve_raw_file(
        raw_file_hash=raw_file_hash,
        processed_s3_key=processed_s3_key,
        canonical_hash=canonical_hash,
        document_id=document_id,
        now=now,
    )

    result = {
        "action": "canonical_document_reused" if reused_existing_document else "canonical_document_created",
        "submissionId": submission_id,
        "fileId": file_id,
        "rawFileHash": raw_file_hash,
        "processedS3Key": processed_s3_key,
        "canonicalHash": canonical_hash,
        "documentId": document_id,
        "canonicalS3Prefix": canonical_s3_prefix,
        "canonicalChunkCount": canonical_chunk_count,
        "reusedExistingDocument": reused_existing_document,
        "kbIngestionStatus": "PENDING_INGESTION",
        "businessDocumentKey": business_document_key,
        "sourceVersion": source_version,
        "sourceUpdatedAt": source_updated_at,
        "isActive": activation_result["isActive"],
    }
    log_info(**result)
    return result


def read_text_from_s3(key: str) -> str:
    response = s3.get_object(Bucket=DOCUMENT_BUCKET_NAME, Key=key)
    return response["Body"].read().decode("utf-8")


def build_document_id(canonical_hash: str) -> str:
    hash_suffix = canonical_hash.split("sha256:", maxsplit=1)[1]
    return f"doc-{hash_suffix[:16]}"


def find_document_by_canonical_hash(canonical_hash: str) -> dict[str, Any] | None:
    response = dynamodb.query(
        TableName=DOCUMENT_REGISTRY_TABLE,
        IndexName="canonicalHash-index",
        KeyConditionExpression="canonicalHash = :canonical_hash",
        ExpressionAttributeValues={
            ":canonical_hash": {"S": canonical_hash},
        },
        Limit=1,
        ConsistentRead=False,
    )
    items = response.get("Items", [])
    if not items:
        return None
    return deserialize_item(items[0])


def build_canonical_chunk_records(
    document_id: str,
    canonical_s3_prefix: str,
    canonical_text: str,
) -> list[dict[str, str]]:
    chunks = split_markdown_into_chunks(canonical_text, max_chars=CANONICAL_CHUNK_MAX_CHARS)
    records: list[dict[str, str]] = []
    for index, chunk_text in enumerate(chunks, start=1):
        content_key = f"{canonical_s3_prefix}chunk-{index:04d}.md"
        metadata_key = f"{content_key}.metadata.json"
        records.append(
            {
                "documentId": document_id,
                "chunkIndex": str(index),
                "contentKey": content_key,
                "metadataKey": metadata_key,
                "content": chunk_text,
            }
        )
    return records


def split_markdown_into_chunks(text: str, max_chars: int) -> list[str]:
    normalized = text.strip()
    if normalized == "":
        return [""]

    paragraphs = normalized.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if paragraph == "":
            continue

        paragraph_length = len(paragraph)
        if paragraph_length > max_chars:
            if current_parts:
                chunks.append("\n\n".join(current_parts).strip())
                current_parts = []
                current_length = 0
            chunks.extend(split_large_paragraph(paragraph, max_chars=max_chars))
            continue

        projected_length = current_length + (2 if current_parts else 0) + paragraph_length
        if current_parts and projected_length > max_chars:
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = [paragraph]
            current_length = paragraph_length
        else:
            current_parts.append(paragraph)
            current_length = projected_length if current_parts[:-1] else paragraph_length

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())

    return [chunk for chunk in chunks if chunk != ""]


def split_large_paragraph(paragraph: str, max_chars: int) -> list[str]:
    lines = paragraph.splitlines()
    if len(lines) > 1:
        chunks: list[str] = []
        current_lines: list[str] = []
        current_length = 0
        for line in lines:
            line = line.rstrip()
            projected_length = current_length + (1 if current_lines else 0) + len(line)
            if current_lines and projected_length > max_chars:
                chunks.append("\n".join(current_lines).strip())
                current_lines = [line]
                current_length = len(line)
            else:
                current_lines.append(line)
                current_length = projected_length if current_lines[:-1] else len(line)
        if current_lines:
            chunks.append("\n".join(current_lines).strip())
        return [chunk for chunk in chunks if chunk != ""]

    return [paragraph[index:index + max_chars].strip() for index in range(0, len(paragraph), max_chars) if paragraph[index:index + max_chars].strip()]


def create_canonical_document(
    document_id: str,
    canonical_hash: str,
    canonical_s3_prefix: str,
    chunk_records: list[dict[str, str]],
    business_document_key: str | None,
    source_version: str | None,
    source_updated_at: str | None,
    now: str,
) -> None:
    write_canonical_chunks(chunk_records)
    ensure_canonical_chunks_persisted(
        canonical_s3_prefix=canonical_s3_prefix,
        chunk_records=chunk_records,
    )

    try:
        item = {
            "documentId": {"S": document_id},
            "canonicalHash": {"S": canonical_hash},
            "canonicalS3Prefix": {"S": canonical_s3_prefix},
            "canonicalChunkCount": {"N": str(len(chunk_records))},
            "kbIngestionStatus": {"S": "PENDING_INGESTION"},
            "isActive": {"BOOL": False},
            "createdAt": {"S": now},
            "updatedAt": {"S": now},
        }
        if business_document_key is not None:
            item["businessDocumentKey"] = {"S": business_document_key}
        if source_version is not None:
            item["sourceVersion"] = {"S": source_version}
        if source_updated_at is not None:
            item["sourceUpdatedAt"] = {"S": source_updated_at}
        dynamodb.put_item(
            TableName=DOCUMENT_REGISTRY_TABLE,
            Item=item,
            ConditionExpression="attribute_not_exists(documentId)",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def write_canonical_chunks(chunk_records: list[dict[str, str]]) -> None:
    for record in chunk_records:
        s3.put_object(
            Bucket=DOCUMENT_BUCKET_NAME,
            Key=record["contentKey"],
            Body=record["content"].encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )
        s3.put_object(
            Bucket=DOCUMENT_BUCKET_NAME,
            Key=record["metadataKey"],
            Body=json.dumps({"metadataAttributes": {"documentId": record["documentId"]}}, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )


def ensure_canonical_chunks_persisted(
    canonical_s3_prefix: str,
    chunk_records: list[dict[str, str]],
) -> None:
    missing_keys = find_missing_chunk_keys(
        canonical_s3_prefix=canonical_s3_prefix,
        chunk_records=chunk_records,
    )
    if not missing_keys:
        log_info(
            action="canonical_chunk_persistence_verified",
            canonicalS3Prefix=canonical_s3_prefix,
            expectedObjectCount=len(chunk_records) * 2,
            missingObjectCount=0,
        )
        return

    log_info(
        action="canonical_chunk_persistence_retry",
        canonicalS3Prefix=canonical_s3_prefix,
        expectedObjectCount=len(chunk_records) * 2,
        missingObjectCount=len(missing_keys),
        missingKeysSample=sorted(list(missing_keys))[:10],
    )

    for record in chunk_records:
        if record["contentKey"] in missing_keys:
            s3.put_object(
                Bucket=DOCUMENT_BUCKET_NAME,
                Key=record["contentKey"],
                Body=record["content"].encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
        if record["metadataKey"] in missing_keys:
            s3.put_object(
                Bucket=DOCUMENT_BUCKET_NAME,
                Key=record["metadataKey"],
                Body=json.dumps({"metadataAttributes": {"documentId": record["documentId"]}}, sort_keys=True).encode("utf-8"),
                ContentType="application/json",
            )

    remaining_missing_keys = find_missing_chunk_keys(
        canonical_s3_prefix=canonical_s3_prefix,
        chunk_records=chunk_records,
    )
    if remaining_missing_keys:
        log_info(
            action="canonical_chunk_persistence_failed",
            canonicalS3Prefix=canonical_s3_prefix,
            expectedObjectCount=len(chunk_records) * 2,
            missingObjectCount=len(remaining_missing_keys),
            missingKeysSample=sorted(list(remaining_missing_keys))[:10],
        )
        raise RuntimeError(
            f"Canonical chunk persistence verification failed for {canonical_s3_prefix}: "
            f"{len(remaining_missing_keys)} keys missing after retry."
        )

    log_info(
        action="canonical_chunk_persistence_verified",
        canonicalS3Prefix=canonical_s3_prefix,
        expectedObjectCount=len(chunk_records) * 2,
        missingObjectCount=0,
    )


def find_missing_chunk_keys(
    canonical_s3_prefix: str,
    chunk_records: list[dict[str, str]],
) -> set[str]:
    expected_keys = {
        key
        for record in chunk_records
        for key in (record["contentKey"], record["metadataKey"])
    }
    actual_keys = list_s3_keys(prefix=canonical_s3_prefix)
    return expected_keys - actual_keys


def list_s3_keys(prefix: str) -> set[str]:
    paginator = s3.get_paginator("list_objects_v2")
    keys: set[str] = set()
    for page in paginator.paginate(Bucket=DOCUMENT_BUCKET_NAME, Prefix=prefix):
        for item in page.get("Contents", []):
            keys.add(item["Key"])
    return keys


def update_existing_document_metadata(
    document_id: str,
    business_document_key: str | None,
    source_version: str | None,
    source_updated_at: str | None,
    now: str,
) -> None:
    update_clauses = ["#updatedAt = :updated_at"]
    expression_attribute_names = {
        "#updatedAt": "updatedAt",
    }
    expression_attribute_values = {
        ":updated_at": {"S": now},
    }

    if business_document_key is not None:
        update_clauses.append("#businessDocumentKey = :business_document_key")
        expression_attribute_names["#businessDocumentKey"] = "businessDocumentKey"
        expression_attribute_values[":business_document_key"] = {"S": business_document_key}
    if source_version is not None:
        update_clauses.append("#sourceVersion = :source_version")
        expression_attribute_names["#sourceVersion"] = "sourceVersion"
        expression_attribute_values[":source_version"] = {"S": source_version}
    if source_updated_at is not None:
        update_clauses.append("#sourceUpdatedAt = :source_updated_at")
        expression_attribute_names["#sourceUpdatedAt"] = "sourceUpdatedAt"
        expression_attribute_values[":source_updated_at"] = {"S": source_updated_at}

    dynamodb.update_item(
        TableName=DOCUMENT_REGISTRY_TABLE,
        Key={"documentId": {"S": document_id}},
        UpdateExpression=f"SET {', '.join(update_clauses)}",
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
    )


def determine_active_document(
    document_id: str,
    business_document_key: str | None,
    source_version: str | None,
    source_updated_at: str | None,
    now: str,
) -> dict[str, Any]:
    if business_document_key is None:
        return {"isActive": False}

    current_active = find_active_document_by_business_key(business_document_key)
    should_activate = should_activate_candidate(
        candidate_document_id=document_id,
        candidate_source_version=source_version,
        candidate_source_updated_at=source_updated_at,
        current_active=current_active,
    )

    if should_activate and current_active and current_active["documentId"] != document_id:
        set_document_active_flag(current_active["documentId"], False, now)

    set_document_active_flag(document_id, should_activate, now)
    return {"isActive": should_activate}


def find_active_document_by_business_key(business_document_key: str) -> dict[str, Any] | None:
    response = dynamodb.query(
        TableName=DOCUMENT_REGISTRY_TABLE,
        IndexName="businessDocumentKey-index",
        KeyConditionExpression="businessDocumentKey = :business_document_key",
        ExpressionAttributeValues={
            ":business_document_key": {"S": business_document_key},
        },
        ConsistentRead=False,
    )
    for item in response.get("Items", []):
        deserialized = deserialize_item(item)
        if deserialized.get("isActive") is True:
            return deserialized
    return None


def should_activate_candidate(
    candidate_document_id: str,
    candidate_source_version: str | None,
    candidate_source_updated_at: str | None,
    current_active: dict[str, Any] | None,
) -> bool:
    if current_active is None:
        return True
    if current_active["documentId"] == candidate_document_id:
        return True

    candidate_order = build_order_value(candidate_source_version, candidate_source_updated_at)
    current_order = build_order_value(
        normalize_optional_string(current_active.get("sourceVersion")),
        normalize_optional_string(current_active.get("sourceUpdatedAt")),
    )

    if candidate_order is None or current_order is None:
        return True
    return candidate_order >= current_order


def build_order_value(source_version: str | None, source_updated_at: str | None) -> tuple[str, str] | None:
    if source_version is not None:
        return ("version", source_version)
    if source_updated_at is not None:
        return ("updated_at", source_updated_at)
    return None


def set_document_active_flag(document_id: str, is_active: bool, now: str) -> None:
    dynamodb.update_item(
        TableName=DOCUMENT_REGISTRY_TABLE,
        Key={"documentId": {"S": document_id}},
        UpdateExpression="SET #isActive = :is_active, #updatedAt = :updated_at",
        ExpressionAttributeNames={
            "#isActive": "isActive",
            "#updatedAt": "updatedAt",
        },
        ExpressionAttributeValues={
            ":is_active": {"BOOL": is_active},
            ":updated_at": {"S": now},
        },
    )


def resolve_raw_file(
    raw_file_hash: str,
    processed_s3_key: str,
    canonical_hash: str,
    document_id: str,
    now: str,
) -> None:
    dynamodb.update_item(
        TableName=RAW_FILE_REGISTRY_TABLE,
        Key={"rawFileHash": {"S": raw_file_hash}},
        UpdateExpression=(
            "SET #status = :status, "
            "#processedS3Key = :processed_s3_key, "
            "#canonicalHash = :canonical_hash, "
            "#documentId = :document_id, "
            "#lastSeenAt = :last_seen_at, "
            "#updatedAt = :updated_at"
        ),
        ExpressionAttributeNames={
            "#status": "status",
            "#processedS3Key": "processedS3Key",
            "#canonicalHash": "canonicalHash",
            "#documentId": "documentId",
            "#lastSeenAt": "lastSeenAt",
            "#updatedAt": "updatedAt",
        },
        ExpressionAttributeValues={
            ":status": {"S": "RESOLVED"},
            ":processed_s3_key": {"S": processed_s3_key},
            ":canonical_hash": {"S": canonical_hash},
            ":document_id": {"S": document_id},
            ":last_seen_at": {"S": now},
            ":updated_at": {"S": now},
        },
    )


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserializer.deserialize(value) for key, value in item.items()}


def is_compatible_business_key(existing_document: dict[str, Any], business_document_key: str | None) -> bool:
    existing_key = normalize_optional_string(existing_document.get("businessDocumentKey"))
    if business_document_key is None or existing_key is None:
        return True
    return existing_key == business_document_key


def normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
