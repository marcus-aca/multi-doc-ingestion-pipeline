from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer


ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = ROOT / "terraform"
DESERIALIZER = TypeDeserializer()


@dataclass
class Phase14Context:
    outputs: dict[str, Any]
    lambda_client: Any
    s3_client: Any
    dynamodb_client: Any
    stepfunctions_client: Any

    @property
    def region(self) -> str:
        return self.outputs["aws_region"]

    @property
    def document_bucket_name(self) -> str:
        return self.outputs["document_bucket_name"]

    @property
    def completion_trigger_lambda_name(self) -> str:
        return self.outputs["completion_trigger_lambda_name"]

    @property
    def upload_event_handler_lambda_name(self) -> str:
        return self.outputs["upload_event_handler_lambda_name"]

    @property
    def query_api_lambda_name(self) -> str:
        return self.outputs["query_api_lambda_name"]

    @property
    def kb_coordinator_lambda_name(self) -> str:
        return self.outputs["kb_coordinator_lambda_name"]

    @property
    def submission_registry_table_name(self) -> str:
        return self.outputs["submission_registry_table_name"]

    @property
    def document_registry_table_name(self) -> str:
        return self.outputs["document_registry_table_name"]


def create_context() -> Phase14Context:
    outputs = load_terraform_outputs()
    session = boto3.Session(region_name=outputs["aws_region"])
    return Phase14Context(
        outputs=outputs,
        lambda_client=session.client("lambda"),
        s3_client=session.client("s3"),
        dynamodb_client=session.client("dynamodb"),
        stepfunctions_client=session.client("stepfunctions"),
    )


def load_terraform_outputs() -> dict[str, Any]:
    result = subprocess.run(
        ["terraform", "-chdir=terraform", "output", "-json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    raw_outputs = json.loads(result.stdout)
    return {name: details["value"] for name, details in raw_outputs.items()}


def load_manifest(manifest_path: str | Path, run_id: str | None = None) -> dict[str, Any]:
    resolved_path = resolve_repo_path(manifest_path)
    manifest = json.loads(resolved_path.read_text(encoding="utf-8"))
    if "files" not in manifest or not isinstance(manifest["files"], list) or not manifest["files"]:
        raise ValueError(f"Manifest {resolved_path} must define a non-empty 'files' list.")

    resolved = copy.deepcopy(manifest)
    resolved["manifestPath"] = str(resolved_path)
    resolved["submissionId"] = resolve_submission_id(resolved, run_id=run_id)
    return resolved


def resolve_submission_id(manifest: dict[str, Any], run_id: str | None = None) -> str:
    if manifest.get("submissionId"):
        return str(manifest["submissionId"])
    template = manifest.get("submissionIdTemplate")
    if not template:
        raise ValueError("Manifest must define either 'submissionId' or 'submissionIdTemplate'.")
    if run_id is None:
        raise ValueError("Manifest uses 'submissionIdTemplate', so a run id is required.")
    return str(template).format(run_id=run_id)


def resolve_repo_path(path_value: str | Path) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def materialize_manifest_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for file_spec in manifest["files"]:
        source_path = resolve_repo_path(file_spec["source"])
        raw_bytes = build_file_bytes(source_path=source_path, transform=file_spec.get("transform"))
        files.append(
            {
                "fileId": file_spec["fileId"],
                "sourcePath": str(source_path),
                "logicalName": file_spec.get("logicalName", file_spec["fileId"]),
                "transform": file_spec.get("transform", {"type": "verbatim"}),
                "rawBytes": raw_bytes,
                "rawFileHash": sha256_digest(raw_bytes),
                "canonicalHash": canonical_hash_for_json_bytes(raw_bytes),
            }
        )
    return files


def build_file_bytes(source_path: Path, transform: dict[str, Any] | None) -> bytes:
    source_bytes = source_path.read_bytes()
    transform_type = (transform or {}).get("type", "verbatim")
    if transform_type == "verbatim":
        return source_bytes

    source_json = json.loads(source_bytes.decode("utf-8"))
    if transform_type == "compact_json":
        return json.dumps(source_json, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if transform_type == "update_top_level_fields":
        if not isinstance(source_json, dict):
            raise ValueError("update_top_level_fields requires a JSON object source document.")
        updated_json = dict(source_json)
        for key, value in (transform.get("fields") or {}).items():
            updated_json[key] = value
        return json.dumps(updated_json, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"

    raise ValueError(f"Unsupported transform type: {transform_type}")


def sha256_digest(raw_bytes: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"


def canonical_hash_for_json_bytes(raw_bytes: bytes) -> str:
    source_json = json.loads(raw_bytes.decode("utf-8"))
    sanitized_json = remove_segment_ids(source_json)
    markdown_text = render_json_as_markdown(sanitized_json)
    canonical_source = {
        "normalizationStrategy": "json_to_markdown_lines_v2",
        "markdownText": markdown_text,
    }
    canonical_bytes = json.dumps(
        canonical_source,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"


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


def upload_submission(ctx: Phase14Context, manifest: dict[str, Any]) -> dict[str, Any]:
    materialized_files = materialize_manifest_files(manifest)
    uploaded_keys = []
    for file_spec in materialized_files:
        key = f"ingestion/{manifest['submissionId']}/{file_spec['fileId']}"
        ctx.s3_client.put_object(
            Bucket=ctx.document_bucket_name,
            Key=key,
            Body=file_spec["rawBytes"],
            ContentType="application/json",
        )
        uploaded_keys.append(key)

    return {
        "submissionId": manifest["submissionId"],
        "bucket": ctx.document_bucket_name,
        "uploadedKeys": uploaded_keys,
        "files": materialized_files,
    }


def trigger_completion(ctx: Phase14Context, submission_id: str, expected_file_ids: list[str]) -> dict[str, Any]:
    return invoke_lambda_json(
        ctx.lambda_client,
        ctx.completion_trigger_lambda_name,
        {
            "submissionId": submission_id,
            "expectedFileIds": expected_file_ids,
        },
    )


def wait_for_submission_files(
    ctx: Phase14Context,
    submission_id: str,
    expected_file_ids: list[str],
    timeout_seconds: int = 60,
    poll_seconds: int = 2,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    expected_set = set(expected_file_ids)
    replayed_missing_events = False

    while time.monotonic() < deadline:
        submission = get_submission(ctx, submission_id)
        actual_file_ids = set(submission.get("fileIds", []))
        if expected_set.issubset(actual_file_ids):
            return submission

        if not replayed_missing_events and time.monotonic() + poll_seconds >= deadline:
            for missing_file_id in sorted(expected_set - actual_file_ids):
                replay_upload_event(ctx, submission_id, missing_file_id)
            replayed_missing_events = True
        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Timed out waiting for submission {submission_id} to record files {sorted(expected_set)} in SubmissionRegistry."
    )


def replay_upload_event(ctx: Phase14Context, submission_id: str, file_id: str) -> dict[str, Any]:
    key = f"ingestion/{submission_id}/{file_id}"
    return invoke_lambda_json(
        ctx.lambda_client,
        ctx.upload_event_handler_lambda_name,
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": ctx.document_bucket_name},
                        "object": {
                            "key": key,
                            "sequencer": "phase14-replayed-event",
                        },
                    },
                }
            ]
        },
    )


def invoke_scoped_query(
    ctx: Phase14Context,
    submission_id: str,
    query_text: str,
    max_results: int = 5,
) -> dict[str, Any]:
    return invoke_lambda_json(
        ctx.lambda_client,
        ctx.query_api_lambda_name,
        {
            "submissionId": submission_id,
            "queryText": query_text,
            "maxResults": max_results,
        },
    )


def run_kb_coordinator(ctx: Phase14Context) -> dict[str, Any]:
    return invoke_lambda_json(ctx.lambda_client, ctx.kb_coordinator_lambda_name, {})


def invoke_lambda_json(lambda_client: Any, function_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    payload_bytes = response["Payload"].read()
    payload_data = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else {}
    if "FunctionError" in response:
        raise RuntimeError(f"Lambda {function_name} failed: {json.dumps(payload_data, indent=2)}")
    return payload_data


def get_submission(ctx: Phase14Context, submission_id: str) -> dict[str, Any]:
    response = ctx.dynamodb_client.get_item(
        TableName=ctx.submission_registry_table_name,
        Key={"submissionId": {"S": submission_id}},
        ConsistentRead=True,
    )
    return deserialize_item(response.get("Item", {}))


def get_document(ctx: Phase14Context, document_id: str) -> dict[str, Any]:
    response = ctx.dynamodb_client.get_item(
        TableName=ctx.document_registry_table_name,
        Key={"documentId": {"S": document_id}},
        ConsistentRead=True,
    )
    return deserialize_item(response.get("Item", {}))


def query_documents_by_business_key(ctx: Phase14Context, business_document_key: str) -> list[dict[str, Any]]:
    response = ctx.dynamodb_client.query(
        TableName=ctx.document_registry_table_name,
        IndexName="businessDocumentKey-index",
        KeyConditionExpression="businessDocumentKey = :business_document_key",
        ExpressionAttributeValues={
            ":business_document_key": {"S": business_document_key},
        },
        ConsistentRead=False,
    )
    return [deserialize_item(item) for item in response.get("Items", [])]


def describe_execution(ctx: Phase14Context, execution_arn: str) -> dict[str, Any]:
    return ctx.stepfunctions_client.describe_execution(executionArn=execution_arn)


def wait_for_submission_terminal(
    ctx: Phase14Context,
    submission_id: str,
    execution_arn: str | None = None,
    timeout_seconds: int = 900,
    poll_seconds: int = 10,
    drive_kb_coordinator: bool = False,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = None

    while time.monotonic() < deadline:
        submission = get_submission(ctx, submission_id)
        submission_status = submission.get("status", "MISSING")
        execution_status = None
        if execution_arn:
            execution_status = describe_execution(ctx, execution_arn).get("status")

        if submission_status != last_status and submission_status != "READY":
            last_status = submission_status

        if submission_status in {"READY", "FAILED"}:
            return {
                "submission": submission,
                "executionStatus": execution_status,
            }

        if execution_status in {"FAILED", "TIMED_OUT", "ABORTED"}:
            return {
                "submission": submission,
                "executionStatus": execution_status,
            }

        if drive_kb_coordinator and submission_status in {"COMPLETE", "WAITING_FOR_INDEX"}:
            run_kb_coordinator(ctx)

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Timed out waiting for submission {submission_id} to reach READY or FAILED after {timeout_seconds} seconds."
    )


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: DESERIALIZER.deserialize(value) for key, value in item.items()}


def utc_run_id() -> str:
    return time.strftime("%Y%m%d%H%M%S", time.gmtime())
