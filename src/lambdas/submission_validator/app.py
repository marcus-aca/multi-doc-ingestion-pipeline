import json
import logging
from typing import Any


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def _decode_string_list(attribute: dict[str, Any] | None) -> list[str]:
    if not attribute or "L" not in attribute:
        return []
    return [item["S"] for item in attribute["L"]]


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    item = event.get("submissionItem")
    expected_file_ids = event.get("expectedFileIds", [])
    submission_id = event.get("submissionId", "")

    if not item:
        result = {
            "isValid": False,
            "reason": "SUBMISSION_NOT_FOUND",
            "missingFileIds": expected_file_ids,
        }
        log_info(
            action="submission_validation_completed",
            submissionId=submission_id,
            expectedFileIds=expected_file_ids,
            **result,
        )
        return result

    actual_file_ids = _decode_string_list(item.get("fileIds"))
    missing_file_ids = [file_id for file_id in expected_file_ids if file_id not in actual_file_ids]

    result = {
        "isValid": len(missing_file_ids) == 0,
        "reason": "OK" if not missing_file_ids else "MISSING_FILES",
        "missingFileIds": missing_file_ids,
        "actualFileIds": actual_file_ids,
        "receivedFileCount": int(item.get("receivedFileCount", {}).get("N", "0")),
        "status": item.get("status", {}).get("S", ""),
    }
    log_info(
        action="submission_validation_completed",
        submissionId=submission_id,
        expectedFileIds=expected_file_ids,
        **result,
    )
    return result


def log_info(**fields: Any) -> None:
    LOGGER.info(json.dumps(fields, sort_keys=True))
