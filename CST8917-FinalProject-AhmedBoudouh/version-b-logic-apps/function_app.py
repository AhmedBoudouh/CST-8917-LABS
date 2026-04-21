"""
CST8917 Final Project - Version B: Logic Apps + Service Bus
Supporting Azure Function (HTTP) - Expense Validator

Author : Ahmed Boudouh (041162807)
Date   : 2026-04-18

Role in Version B:
    The Logic App is the orchestrator. It receives messages from a Service
    Bus queue (expense-requests) and calls THIS function as its first step
    to validate the payload. Based on the boolean `is_valid` result the
    Logic App either publishes a rejection to the Service Bus topic or
    continues the approval workflow.

    This function is kept deliberately thin - all orchestration lives in
    the Logic App. That is the whole point of the comparison.

Endpoint:
    POST /api/validate
    Body: expense request JSON (same schema as Version A)
    Returns:
        { "is_valid": true|false, "errors": [...], "normalized": {...} }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import azure.functions as func

VALID_CATEGORIES: set[str] = {
    "travel",
    "meals",
    "supplies",
    "equipment",
    "software",
    "other",
}

REQUIRED_FIELDS: list[str] = [
    "employee_name",
    "employee_email",
    "amount",
    "category",
    "description",
    "manager_email",
]

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="validate", methods=["POST"])
def validate(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload: dict[str, Any] = req.get_json()
    except ValueError:
        return _json_response(
            {"is_valid": False, "errors": ["Request body must be valid JSON"]},
            status=400,
        )

    errors: list[str] = []

    # Required field presence
    for field in REQUIRED_FIELDS:
        if field not in payload or payload[field] in (None, ""):
            errors.append(f"Missing required field: {field}")

    # Amount must be positive number
    amount = payload.get("amount")
    if amount is not None:
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append("amount must be greater than zero")
        except (TypeError, ValueError):
            errors.append("amount must be a number")

    # Category must be one of the allowed values
    category = payload.get("category")
    if category is not None and str(category).lower() not in VALID_CATEGORIES:
        errors.append(f"category must be one of: {sorted(VALID_CATEGORIES)}")

    # Very light email sanity check
    for email_field in ("employee_email", "manager_email"):
        value = payload.get(email_field)
        if value and "@" not in str(value):
            errors.append(f"{email_field} does not look like an email address")

    is_valid = len(errors) == 0
    result: dict[str, Any] = {"is_valid": is_valid, "errors": errors}

    if is_valid:
        result["normalized"] = {
            "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
            "employee_name": str(payload["employee_name"]).strip(),
            "employee_email": str(payload["employee_email"]).strip().lower(),
            "manager_email": str(payload["manager_email"]).strip().lower(),
            "amount": round(float(payload["amount"]), 2),
            "category": str(payload["category"]).lower(),
            "description": str(payload["description"]).strip(),
            "requires_manager_approval": float(payload["amount"]) >= 100.0,
        }

    logging.info(
        "Validation complete: is_valid=%s errors=%d", is_valid, len(errors)
    )
    return _json_response(result, status=200)


def _json_response(body: dict[str, Any], status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(body),
        status_code=status,
        mimetype="application/json",
    )
