import json
import logging
import os
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")
deserializer = TypeDeserializer()

SUBMISSION_REGISTRY_TABLE = os.environ["SUBMISSION_REGISTRY_TABLE"]
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
SONNET_MODEL_ID = os.environ["SONNET_MODEL_ID"]
SONNET_INFERENCE_PROFILE_ID = os.environ.get("SONNET_INFERENCE_PROFILE_ID", SONNET_MODEL_ID)
DEFAULT_MAX_RESULTS = int(os.environ.get("QUERY_API_DEFAULT_MAX_RESULTS", "5"))
MAX_SNIPPET_CHARS = int(os.environ.get("QUERY_API_MAX_SNIPPET_CHARS", "1200"))
MAX_MODEL_SNIPPETS = int(os.environ.get("QUERY_API_MAX_MODEL_SNIPPETS", "4"))
DEFAULT_MAX_TOKENS = int(os.environ.get("QUERY_API_MAX_TOKENS", "400"))


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    submission_id = event["submissionId"]
    query_text = event["queryText"].strip()
    max_results = max(1, min(int(event.get("maxResults", DEFAULT_MAX_RESULTS)), 10))

    submission = get_submission(submission_id)
    document_ids = submission.get("documentIds", [])
    submission_status = submission.get("status", "UNKNOWN")

    if not document_ids:
        result = {
            "action": "scoped_query_no_documents",
            "submissionId": submission_id,
            "queryText": query_text,
            "submissionStatus": submission_status,
            "documentIds": [],
            "retrievalResultCount": 0,
            "retrievedDocumentIds": [],
        "summaryText": "Summary placeholder: no documents are linked to this submission.",
        "modelInvoked": False,
        "modelId": SONNET_MODEL_ID,
        "modelInvocationId": SONNET_INFERENCE_PROFILE_ID,
        }
        log_info(**result)
        return result

    retrieve_response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query_text},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": max_results,
                "filter": build_document_filter(document_ids),
            }
        },
    )

    retrieval_results = retrieve_response.get("retrievalResults", [])
    normalized_results = normalize_retrieval_results(retrieval_results)
    retrieved_document_ids = sorted({item["documentId"] for item in normalized_results if item["documentId"]})

    summary_text = build_placeholder_summary(submission_id, query_text, normalized_results)
    model_invoked = False
    model_invocation_error = None
    if normalized_results:
        try:
            summary_text = invoke_sonnet(submission_id, query_text, normalized_results)
            model_invoked = True
        except Exception as error:
            model_invocation_error = f"{type(error).__name__}: {error}"

    result = {
        "action": "scoped_query_completed",
        "submissionId": submission_id,
        "queryText": query_text,
        "submissionStatus": submission_status,
        "documentIds": document_ids,
        "retrievalResultCount": len(normalized_results),
        "retrievedDocumentIds": retrieved_document_ids,
        "retrievalResults": normalized_results,
        "summaryText": summary_text,
        "modelInvoked": model_invoked,
        "modelId": SONNET_MODEL_ID,
        "modelInvocationId": SONNET_INFERENCE_PROFILE_ID,
        "modelInvocationError": model_invocation_error,
    }
    log_info(
        action=result["action"],
        submissionId=submission_id,
        queryText=query_text,
        submissionStatus=submission_status,
        documentIds=document_ids,
        retrievalResultCount=len(normalized_results),
        retrievedDocumentIds=retrieved_document_ids,
        modelInvoked=model_invoked,
        modelId=SONNET_MODEL_ID,
        modelInvocationId=SONNET_INFERENCE_PROFILE_ID,
        modelInvocationError=model_invocation_error,
    )
    return result


def get_submission(submission_id: str) -> dict[str, Any]:
    response = dynamodb.get_item(
        TableName=SUBMISSION_REGISTRY_TABLE,
        Key={"submissionId": {"S": submission_id}},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if not item:
        raise ValueError(f"Submission '{submission_id}' was not found.")
    return deserialize_item(item)


def build_document_filter(document_ids: list[str]) -> dict[str, Any]:
    filters = [
        {"equals": {"key": "documentId", "value": document_id}}
        for document_id in document_ids
    ]
    if len(filters) == 1:
        return filters[0]
    return {"orAll": filters}


def normalize_retrieval_results(retrieval_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in retrieval_results:
        metadata = item.get("metadata") or {}
        content = item.get("content") or {}
        text = (content.get("text") or "")[:MAX_SNIPPET_CHARS]
        location = item.get("location") or {}
        score = item.get("score")
        normalized.append(
            {
                "documentId": metadata.get("documentId"),
                "score": score,
                "contentType": content.get("type"),
                "text": text,
                "s3Uri": extract_s3_uri(location),
                "metadata": metadata,
            }
        )
    return normalized


def extract_s3_uri(location: dict[str, Any]) -> str | None:
    s3_location = location.get("s3Location") or {}
    return s3_location.get("uri")


def build_placeholder_summary(submission_id: str, query_text: str, retrieval_results: list[dict[str, Any]]) -> str:
    if not retrieval_results:
        return (
            f"Summary placeholder: no scoped matches were found for submission {submission_id} "
            f"for query '{query_text}'."
        )
    return (
        f"Summary placeholder: retrieved {len(retrieval_results)} scoped chunks for submission {submission_id} "
        f"for query '{query_text}'."
    )


def invoke_sonnet(submission_id: str, query_text: str, retrieval_results: list[dict[str, Any]]) -> str:
    prompt_sections = []
    for index, item in enumerate(retrieval_results[:MAX_MODEL_SNIPPETS], start=1):
        prompt_sections.append(
            "\n".join(
                [
                    f"Result {index}",
                    f"documentId: {item.get('documentId')}",
                    f"s3Uri: {item.get('s3Uri')}",
                    f"score: {item.get('score')}",
                    item.get("text", ""),
                ]
            )
        )

    prompt = "\n\n".join(
        [
            "You are answering with only the provided scoped retrieval results.",
            f"Submission ID: {submission_id}",
            f"User query: {query_text}",
            "Provide a short answer grounded only in these snippets. If the answer is not present, say so plainly.",
            "",
            *prompt_sections,
        ]
    )

    response = bedrock_runtime.invoke_model(
        modelId=SONNET_INFERENCE_PROFILE_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": DEFAULT_MAX_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
            }
        ),
    )
    response_body = json.loads(response["body"].read())
    return extract_model_text(response_body)


def extract_model_text(response_body: dict[str, Any]) -> str:
    content = response_body.get("content") or []
    text_parts = []
    for item in content:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    return "\n".join(part for part in text_parts if part).strip()


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserializer.deserialize(value) for key, value in item.items()}


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
