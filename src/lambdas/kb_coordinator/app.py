import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

bedrock_agent = boto3.client("bedrock-agent")
dynamodb = boto3.client("dynamodb")
deserializer = TypeDeserializer()

DOCUMENT_REGISTRY_TABLE = os.environ["DOCUMENT_REGISTRY_TABLE"]
INGESTION_RUN_TABLE = os.environ["INGESTION_RUN_TABLE"]
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")
DATA_SOURCE_ID = os.environ.get("DATA_SOURCE_ID", "")
BATCH_SIZE = int(os.environ.get("KB_COORDINATOR_BATCH_SIZE", "10"))

IN_PROGRESS_JOB_STATUSES = {"STARTING", "IN_PROGRESS", "STOPPING"}
TERMINAL_JOB_STATUSES = {"COMPLETE", "FAILED", "STOPPED"}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    active_run = find_active_ingestion_run()
    if active_run is not None:
        result = poll_ingestion_run(active_run)
        log_info(**result)
        return result

    pending_documents = list_pending_documents(limit=BATCH_SIZE)
    if not pending_documents:
        result = {
            "action": "kb_coordinator_no_pending_documents",
            "documentCount": 0,
            "knowledgeBaseConfigured": is_kb_configured(),
        }
        log_info(**result)
        return result

    if not is_kb_configured():
        result = {
            "action": "kb_coordinator_missing_configuration",
            "documentCount": len(pending_documents),
            "documentIds": [item["documentId"] for item in pending_documents],
            "knowledgeBaseConfigured": False,
        }
        log_info(**result)
        return result

    ingestion_run_id = f"run-{uuid.uuid4()}"
    now = utc_now()
    document_ids = [item["documentId"] for item in pending_documents]
    create_ingestion_run(
        ingestion_run_id=ingestion_run_id,
        document_ids=document_ids,
        now=now,
    )
    log_info(
        action="kb_coordinator_documents_selected",
        ingestionRunId=ingestion_run_id,
        documentCount=len(pending_documents),
        documents=summarize_documents(pending_documents),
    )
    set_documents_ingestion_status(
        document_ids=document_ids,
        status="INGESTING",
        now=now,
        pending_ingestion_run_id=ingestion_run_id,
    )

    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=DATA_SOURCE_ID,
            clientToken=build_client_token(ingestion_run_id),
            description=f"POC KB sync for {ingestion_run_id}",
        )
    except Exception as error:
        set_documents_ingestion_status(
            document_ids=document_ids,
            status="FAILED",
            now=utc_now(),
            pending_ingestion_run_id=None,
            last_error=str(error),
        )
        finalize_ingestion_run(
            ingestion_run_id=ingestion_run_id,
            kb_operation_id=None,
            status="FAILED",
            error_summary=str(error)[:2048],
            completed_at=utc_now(),
        )
        log_info(
            action="kb_coordinator_ingestion_submit_failed",
            ingestionRunId=ingestion_run_id,
            errorType=type(error).__name__,
            errorMessage=str(error),
        )
        raise

    ingestion_job = response.get("ingestionJob", {})
    kb_operation_id = ingestion_job.get("ingestionJobId")
    job_status = ingestion_job.get("status", "STARTING")
    log_info(
        action="kb_coordinator_ingestion_response",
        ingestionRunId=ingestion_run_id,
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        dataSourceId=DATA_SOURCE_ID,
        ingestionJob=ingestion_job,
    )

    run_status = determine_job_run_status(ingestion_job)
    finalize_ingestion_run(
        ingestion_run_id=ingestion_run_id,
        kb_operation_id=kb_operation_id,
        status=run_status,
        error_summary=build_job_error_summary(ingestion_job),
        completed_at=utc_now() if job_status in TERMINAL_JOB_STATUSES else None,
    )

    if run_status == "SUCCEEDED":
        set_documents_ingestion_status(
            document_ids=document_ids,
            status="INDEXED",
            now=utc_now(),
            pending_ingestion_run_id=None,
            last_successful_ingestion_run_id=ingestion_run_id,
            clear_last_error=True,
        )
    elif run_status == "FAILED":
        set_documents_ingestion_status(
            document_ids=document_ids,
            status="FAILED",
            now=utc_now(),
            pending_ingestion_run_id=None,
            last_error=build_job_error_summary(ingestion_job),
        )

    result = {
        "action": "kb_coordinator_ingestion_started" if job_status in IN_PROGRESS_JOB_STATUSES or job_status == "STARTING" else "kb_coordinator_ingestion_completed",
        "ingestionRunId": ingestion_run_id,
        "kbOperationId": kb_operation_id,
        "documentCount": len(document_ids),
        "documentIds": document_ids,
        "runStatus": run_status,
        "jobStatus": job_status,
        "knowledgeBaseConfigured": True,
    }
    log_info(**result)
    return result


def is_kb_configured() -> bool:
    return KNOWLEDGE_BASE_ID != "" and DATA_SOURCE_ID != ""


def find_active_ingestion_run() -> dict[str, Any] | None:
    items = scan_filtered_items(
        table_name=INGESTION_RUN_TABLE,
        filter_expression="#status = :started",
        expression_attribute_names={"#status": "status"},
        expression_attribute_values={":started": {"S": "STARTED"}},
        max_items=1,
    )
    if not items:
        return None
    return deserialize_item(items[0])


def list_pending_documents(limit: int) -> list[dict[str, Any]]:
    items = scan_filtered_items(
        table_name=DOCUMENT_REGISTRY_TABLE,
        filter_expression="#kbIngestionStatus = :pending",
        expression_attribute_names={"#kbIngestionStatus": "kbIngestionStatus"},
        expression_attribute_values={":pending": {"S": "PENDING_INGESTION"}},
        max_items=limit,
    )
    return [deserialize_item(item) for item in items]


def scan_filtered_items(
    table_name: str,
    filter_expression: str,
    expression_attribute_names: dict[str, str],
    expression_attribute_values: dict[str, dict[str, Any]],
    max_items: int,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    exclusive_start_key: dict[str, Any] | None = None

    while len(collected) < max_items:
        scan_kwargs: dict[str, Any] = {
            "TableName": table_name,
            "FilterExpression": filter_expression,
            "ExpressionAttributeNames": expression_attribute_names,
            "ExpressionAttributeValues": expression_attribute_values,
        }
        if exclusive_start_key is not None:
            scan_kwargs["ExclusiveStartKey"] = exclusive_start_key

        response = dynamodb.scan(**scan_kwargs)
        collected.extend(response.get("Items", []))
        exclusive_start_key = response.get("LastEvaluatedKey")
        if exclusive_start_key is None:
            break

    return collected[:max_items]


def poll_ingestion_run(active_run: dict[str, Any]) -> dict[str, Any]:
    if not is_kb_configured():
        return {
            "action": "kb_coordinator_active_run_missing_configuration",
            "ingestionRunId": active_run["ingestionRunId"],
            "runStatus": active_run["status"],
            "knowledgeBaseConfigured": False,
        }

    kb_operation_id = active_run.get("kbOperationId")
    document_ids = active_run.get("documentIds", [])
    if not kb_operation_id:
        now = utc_now()
        error_summary = "Active ingestion run is missing kbOperationId."
        set_documents_ingestion_status(
            document_ids=document_ids,
            status="FAILED",
            now=now,
            pending_ingestion_run_id=None,
            last_error=error_summary,
        )
        finalize_ingestion_run(
            ingestion_run_id=active_run["ingestionRunId"],
            kb_operation_id=None,
            status="FAILED",
            error_summary=error_summary,
            completed_at=now,
        )
        return {
            "action": "kb_coordinator_active_run_invalid",
            "ingestionRunId": active_run["ingestionRunId"],
            "documentCount": len(document_ids),
            "runStatus": "FAILED",
            "knowledgeBaseConfigured": True,
            "errorSummary": error_summary,
        }

    response = bedrock_agent.get_ingestion_job(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        dataSourceId=DATA_SOURCE_ID,
        ingestionJobId=kb_operation_id,
    )
    ingestion_job = response.get("ingestionJob", {})
    job_status = ingestion_job.get("status", "FAILED")
    log_info(
        action="kb_coordinator_poll_response",
        ingestionRunId=active_run["ingestionRunId"],
        kbOperationId=kb_operation_id,
        ingestionJob=ingestion_job,
    )

    now = utc_now()
    run_status = determine_job_run_status(ingestion_job)
    if run_status == "SUCCEEDED":
        set_documents_ingestion_status(
            document_ids=document_ids,
            status="INDEXED",
            now=now,
            pending_ingestion_run_id=None,
            last_successful_ingestion_run_id=active_run["ingestionRunId"],
            clear_last_error=True,
        )
    elif run_status == "FAILED":
        set_documents_ingestion_status(
            document_ids=document_ids,
            status="FAILED",
            now=now,
            pending_ingestion_run_id=None,
            last_error=build_job_error_summary(ingestion_job),
        )

    finalize_ingestion_run(
        ingestion_run_id=active_run["ingestionRunId"],
        kb_operation_id=kb_operation_id,
        status=run_status,
        error_summary=build_job_error_summary(ingestion_job),
        completed_at=now if run_status != "STARTED" else None,
    )
    return {
        "action": "kb_coordinator_polled_active_run",
        "ingestionRunId": active_run["ingestionRunId"],
        "kbOperationId": kb_operation_id,
        "documentCount": len(document_ids),
        "runStatus": run_status,
        "jobStatus": job_status,
        "knowledgeBaseConfigured": True,
    }


def create_ingestion_run(ingestion_run_id: str, document_ids: list[str], now: str) -> None:
    dynamodb.put_item(
        TableName=INGESTION_RUN_TABLE,
        Item={
            "ingestionRunId": {"S": ingestion_run_id},
            "status": {"S": "STARTED"},
            "documentIds": {"L": [{"S": document_id} for document_id in document_ids]},
            "startedAt": {"S": now},
        },
        ConditionExpression="attribute_not_exists(ingestionRunId)",
    )


def finalize_ingestion_run(
    ingestion_run_id: str,
    kb_operation_id: str | None,
    status: str,
    error_summary: str | None,
    completed_at: str | None,
) -> None:
    update_clauses = ["#status = :status"]
    expression_attribute_names = {"#status": "status"}
    expression_attribute_values = {":status": {"S": status}}

    if kb_operation_id is not None:
        update_clauses.append("#kbOperationId = :kb_operation_id")
        expression_attribute_names["#kbOperationId"] = "kbOperationId"
        expression_attribute_values[":kb_operation_id"] = {"S": kb_operation_id}
    if error_summary is not None:
        update_clauses.append("#errorSummary = :error_summary")
        expression_attribute_names["#errorSummary"] = "errorSummary"
        expression_attribute_values[":error_summary"] = {"S": error_summary}
    if completed_at is not None:
        update_clauses.append("#completedAt = :completed_at")
        expression_attribute_names["#completedAt"] = "completedAt"
        expression_attribute_values[":completed_at"] = {"S": completed_at}

    dynamodb.update_item(
        TableName=INGESTION_RUN_TABLE,
        Key={"ingestionRunId": {"S": ingestion_run_id}},
        UpdateExpression=f"SET {', '.join(update_clauses)}",
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
    )


def set_documents_ingestion_status(
    document_ids: list[str],
    status: str,
    now: str,
    pending_ingestion_run_id: str | None = None,
    last_successful_ingestion_run_id: str | None = None,
    last_error: str | None = None,
    clear_last_error: bool = False,
) -> None:
    for document_id in document_ids:
        update_document_status(
            document_id=document_id,
            status=status,
            now=now,
            pending_ingestion_run_id=pending_ingestion_run_id,
            last_successful_ingestion_run_id=last_successful_ingestion_run_id,
            last_error=last_error,
            clear_last_error=clear_last_error,
        )


def update_document_status(
    document_id: str,
    status: str,
    now: str,
    pending_ingestion_run_id: str | None,
    last_successful_ingestion_run_id: str | None,
    last_error: str | None,
    clear_last_error: bool,
) -> None:
    update_clauses = ["#kbIngestionStatus = :status", "#updatedAt = :updated_at"]
    expression_attribute_names = {
        "#kbIngestionStatus": "kbIngestionStatus",
        "#updatedAt": "updatedAt",
    }
    expression_attribute_values = {
        ":status": {"S": status},
        ":updated_at": {"S": now},
    }

    update_clauses.append("#pendingIngestionRunId = :pending_ingestion_run_id")
    expression_attribute_names["#pendingIngestionRunId"] = "pendingIngestionRunId"
    if pending_ingestion_run_id is None:
        expression_attribute_values[":pending_ingestion_run_id"] = {"NULL": True}
    else:
        expression_attribute_values[":pending_ingestion_run_id"] = {"S": pending_ingestion_run_id}

    if last_successful_ingestion_run_id is not None:
        update_clauses.append("#lastSuccessfulIngestionRunId = :last_successful_ingestion_run_id")
        expression_attribute_names["#lastSuccessfulIngestionRunId"] = "lastSuccessfulIngestionRunId"
        expression_attribute_values[":last_successful_ingestion_run_id"] = {"S": last_successful_ingestion_run_id}

    if last_error is not None:
        update_clauses.append("#lastIngestionError = :last_ingestion_error")
        expression_attribute_names["#lastIngestionError"] = "lastIngestionError"
        expression_attribute_values[":last_ingestion_error"] = {"S": last_error}
    elif clear_last_error:
        update_clauses.append("#lastIngestionError = :last_ingestion_error")
        expression_attribute_names["#lastIngestionError"] = "lastIngestionError"
        expression_attribute_values[":last_ingestion_error"] = {"NULL": True}

    dynamodb.update_item(
        TableName=DOCUMENT_REGISTRY_TABLE,
        Key={"documentId": {"S": document_id}},
        UpdateExpression=f"SET {', '.join(update_clauses)}",
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
    )


def determine_job_run_status(ingestion_job: dict[str, Any]) -> str:
    job_status = ingestion_job.get("status", "FAILED")
    if job_status in IN_PROGRESS_JOB_STATUSES or job_status == "STARTING":
        return "STARTED"
    if job_status == "COMPLETE" and not job_has_failures(ingestion_job):
        return "SUCCEEDED"
    return "FAILED"


def job_has_failures(ingestion_job: dict[str, Any]) -> bool:
    statistics = ingestion_job.get("statistics") or {}
    if int(statistics.get("numberOfDocumentsFailed", 0) or 0) > 0:
        return True
    return bool(ingestion_job.get("failureReasons"))


def build_job_error_summary(ingestion_job: dict[str, Any]) -> str | None:
    reasons = ingestion_job.get("failureReasons") or []
    if not reasons:
        return None
    return " | ".join(reasons)[:2048]


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


def build_client_token(ingestion_run_id: str) -> str:
    return ingestion_run_id[:256]


def summarize_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "documentId": document["documentId"],
            "canonicalS3Prefix": document.get("canonicalS3Prefix"),
            "canonicalChunkCount": document.get("canonicalChunkCount"),
            "kbIngestionStatus": document.get("kbIngestionStatus"),
        }
        for document in documents
    ]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True, default=str))
