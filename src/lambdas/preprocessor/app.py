import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")
sqs = boto3.client("sqs")

DOCUMENT_BUCKET_NAME = os.environ["DOCUMENT_BUCKET_NAME"]
RAW_FILE_REGISTRY_TABLE = os.environ["RAW_FILE_REGISTRY_TABLE"]
INGESTION_PREFIX = os.environ.get("INGESTION_PREFIX", "ingestion/")
PROCESSED_PREFIX = os.environ.get("PROCESSED_PREFIX", "processed/")
MANUAL_REVIEW_QUEUE_URL = os.environ.get("MANUAL_REVIEW_QUEUE_URL", "")


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    file_id = event["fileId"]
    raw_file_hash = event["rawFileHash"]
    raw_key = f"{INGESTION_PREFIX}{submission_id}/{file_id}"
    processed_key = f"{PROCESSED_PREFIX}{submission_id}/{file_id}.md"

    try:
        if event.get("forceFailure") is True:
            raise ValueError("Forced preprocessor failure for Phase 15 validation.")

        raw_bytes = read_raw_file(raw_key)
        source_json = parse_json_document(raw_bytes)
        sanitized_json = remove_segment_ids(source_json)
        markdown_text = render_json_as_markdown(sanitized_json)
        canonical_hash = build_canonical_hash(markdown_text)

        extracted_metadata = build_extracted_metadata(raw_bytes, source_json, sanitized_json, markdown_text)

        s3.put_object(
            Bucket=DOCUMENT_BUCKET_NAME,
            Key=processed_key,
            Body=markdown_text.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )

        now = utc_now()
        dynamodb.update_item(
            TableName=RAW_FILE_REGISTRY_TABLE,
            Key={"rawFileHash": {"S": raw_file_hash}},
            UpdateExpression=(
                "SET #processedS3Key = :processed_s3_key, "
                "#canonicalHash = :canonical_hash, "
                "#updatedAt = :updated_at"
            ),
            ExpressionAttributeNames={
                "#processedS3Key": "processedS3Key",
                "#canonicalHash": "canonicalHash",
                "#updatedAt": "updatedAt",
            },
            ExpressionAttributeValues={
                ":processed_s3_key": {"S": processed_key},
                ":canonical_hash": {"S": canonical_hash},
                ":updated_at": {"S": now},
            },
        )

        result = {
            "action": "preprocessing_completed",
            "submissionId": submission_id,
            "fileId": file_id,
            "bucket": DOCUMENT_BUCKET_NAME,
            "rawS3Key": raw_key,
            "processedS3Key": processed_key,
            "rawFileHash": raw_file_hash,
            "canonicalHash": canonical_hash,
            "normalizationStrategy": normalization_strategy(),
            "businessDocumentKey": extract_business_document_key(source_json),
            "sourceVersion": extract_source_version(source_json),
            "sourceUpdatedAt": extract_source_updated_at(source_json),
            "extractedMetadata": extracted_metadata,
        }
        log_info(**result)
        return result
    except Exception as error:
        now = utc_now()
        mark_raw_file_failed(raw_file_hash=raw_file_hash, now=now, error_message=str(error))
        enqueue_manual_review(
            {
                "alertType": "preprocessing_failed",
                "submissionId": submission_id,
                "fileId": file_id,
                "rawFileHash": raw_file_hash,
                "rawS3Key": raw_key,
                "processedS3Key": processed_key,
                "errorType": type(error).__name__,
                "errorMessage": str(error),
            }
        )
        log_info(
            action="preprocessing_failed",
            submissionId=submission_id,
            fileId=file_id,
            rawFileHash=raw_file_hash,
            rawS3Key=raw_key,
            processedS3Key=processed_key,
            errorType=type(error).__name__,
            errorMessage=str(error),
        )
        raise


def read_raw_file(key: str) -> bytes:
    response = s3.get_object(Bucket=DOCUMENT_BUCKET_NAME, Key=key)
    return response["Body"].read()


def parse_json_document(raw_bytes: bytes) -> Any:
    decoded_text = raw_bytes.decode("utf-8")
    return json.loads(decoded_text)


def remove_segment_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: remove_segment_ids(child_value)
            for key, child_value in value.items()
            if key != "segment_id"
        }
    if isinstance(value, list):
        return [remove_segment_ids(item) for item in value]
    return value


def render_json_as_markdown(value: Any) -> str:
    rendered_lines: list[str] = []
    render_value(value=value, lines=rendered_lines, indent=0, key_name=None, list_item_prefix=False)
    return "\n".join(line.rstrip() for line in trim_blank_lines(rendered_lines)).strip()


def render_value(
    value: Any,
    lines: list[str],
    indent: int,
    key_name: str | None,
    list_item_prefix: bool,
) -> None:
    if isinstance(value, dict):
        render_dict(value=value, lines=lines, indent=indent, key_name=key_name, list_item_prefix=list_item_prefix)
        return
    if isinstance(value, list):
        render_list(value=value, lines=lines, indent=indent, key_name=key_name, list_item_prefix=list_item_prefix)
        return
    render_scalar(value=value, lines=lines, indent=indent, key_name=key_name, list_item_prefix=list_item_prefix)


def render_dict(
    value: dict[str, Any],
    lines: list[str],
    indent: int,
    key_name: str | None,
    list_item_prefix: bool,
) -> None:
    prefix = build_prefix(indent=indent, key_name=key_name, list_item_prefix=list_item_prefix)
    child_indent = indent + 2 if list_item_prefix else indent

    if prefix is not None:
        lines.append(f"{prefix}:")
    elif lines:
        lines.append("")

    for index, (child_key, child_value) in enumerate(value.items()):
        render_value(
            value=child_value,
            lines=lines,
            indent=child_indent,
            key_name=child_key,
            list_item_prefix=False,
        )
        if index < len(value) - 1:
            lines.append("")


def render_list(
    value: list[Any],
    lines: list[str],
    indent: int,
    key_name: str | None,
    list_item_prefix: bool,
) -> None:
    prefix = build_prefix(indent=indent, key_name=key_name, list_item_prefix=list_item_prefix)
    child_indent = indent + 2 if (key_name is not None or list_item_prefix) else indent

    if prefix is not None:
        lines.append(f"{prefix}:")
    elif lines:
        lines.append("")

    for index, item in enumerate(value):
        if isinstance(item, (dict, list)):
            render_value(
                value=item,
                lines=lines,
                indent=child_indent,
                key_name=None,
                list_item_prefix=True,
            )
        else:
            lines.append(f"{' ' * child_indent}- {format_scalar(item)}")
        if index < len(value) - 1:
            lines.append("")


def render_scalar(
    value: Any,
    lines: list[str],
    indent: int,
    key_name: str | None,
    list_item_prefix: bool,
) -> None:
    formatted_value = format_scalar(value)
    prefix = build_prefix(indent=indent, key_name=key_name, list_item_prefix=list_item_prefix)
    if prefix is None:
        lines.append(f"{' ' * indent}{formatted_value}")
        return

    if "\n" not in formatted_value:
        separator = " " if key_name is None and list_item_prefix else ": "
        lines.append(f"{prefix}{separator}{formatted_value}")
        return

    if key_name is None and list_item_prefix:
        lines.append(f"{prefix} |")
        child_indent = indent + 2
    else:
        lines.append(f"{prefix}: |")
        child_indent = indent + 2

    for line in formatted_value.splitlines():
        lines.append(f"{' ' * child_indent}{line}")


def build_prefix(indent: int, key_name: str | None, list_item_prefix: bool) -> str | None:
    if key_name is None and not list_item_prefix:
        return None
    if key_name is None:
        return f"{' ' * indent}-"
    if list_item_prefix:
        return f"{' ' * indent}- {humanize_key(key_name)}"
    return f"{' ' * indent}{humanize_key(key_name)}"


def format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return normalize_text_block(str(value))


def normalize_text_block(value: str) -> str:
    normalized_lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(normalized_lines).strip()


def humanize_key(key_name: str) -> str:
    return key_name.replace("_", " ").strip().title()


def trim_blank_lines(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and trimmed[0] == "":
        trimmed.pop(0)
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return trimmed


def build_canonical_hash(markdown_text: str) -> str:
    canonical_source = {
        "normalizationStrategy": normalization_strategy(),
        "markdownText": markdown_text,
    }
    canonical_bytes = json.dumps(canonical_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"


def build_extracted_metadata(
    raw_bytes: bytes,
    source_json: Any,
    sanitized_json: Any,
    markdown_text: str,
) -> dict[str, Any]:
    return {
        "byteCount": len(raw_bytes),
        "topLevelType": type(source_json).__name__,
        "topLevelEntryCount": len(source_json) if isinstance(source_json, (dict, list)) else 1,
        "segmentIdRemovedCount": count_segment_ids(source_json),
        "sanitizedTopLevelEntryCount": len(sanitized_json) if isinstance(sanitized_json, (dict, list)) else 1,
        "businessDocumentKey": extract_business_document_key(source_json),
        "sourceVersion": extract_source_version(source_json),
        "sourceUpdatedAt": extract_source_updated_at(source_json),
        "characterCount": len(markdown_text),
        "lineCount": 0 if markdown_text == "" else markdown_text.count("\n") + 1,
    }


def count_segment_ids(value: Any) -> int:
    if isinstance(value, dict):
        current_count = 1 if "segment_id" in value else 0
        return current_count + sum(count_segment_ids(child_value) for child_value in value.values())
    if isinstance(value, list):
        return sum(count_segment_ids(item) for item in value)
    return 0


def extract_business_document_key(source_json: Any) -> str | None:
    if not isinstance(source_json, dict):
        return None
    value = source_json.get("report_id")
    return normalize_optional_string(value)


def extract_source_version(source_json: Any) -> str | None:
    if not isinstance(source_json, dict):
        return None
    value = source_json.get("source_version")
    return normalize_optional_string(value)


def extract_source_updated_at(source_json: Any) -> str | None:
    if not isinstance(source_json, dict):
        return None
    value = source_json.get("report_date") or source_json.get("source_updated_at")
    return normalize_optional_string(value)


def normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalization_strategy() -> str:
    return "json_to_markdown_lines_v2"


def mark_raw_file_failed(raw_file_hash: str, now: str, error_message: str) -> None:
    dynamodb.update_item(
        TableName=RAW_FILE_REGISTRY_TABLE,
        Key={"rawFileHash": {"S": raw_file_hash}},
        UpdateExpression="SET #status = :status, #lastError = :last_error, #updatedAt = :updated_at",
        ExpressionAttributeNames={
            "#status": "status",
            "#lastError": "lastError",
            "#updatedAt": "updatedAt",
        },
        ExpressionAttributeValues={
            ":status": {"S": "FAILED"},
            ":last_error": {"S": error_message[:2048]},
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
