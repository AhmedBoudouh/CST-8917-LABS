"""
CST8917 Final Project - Version A: Azure Durable Functions
Expense Approval Workflow

Author : Ahmed Boudouh (041162807)
Date   : 2026-04-18

Implements the expense approval workflow using the Durable Functions
Python v2 programming model. Demonstrates:

    - Client function (HTTP start)
    - Orchestrator function (workflow)
    - Activity chaining (validate -> process -> notify)
    - Human Interaction pattern with durable timer (timeout auto-escalation)
    - HTTP endpoints for manager approve / reject (raise external event)

Business rules:
    - Required fields  : employee_name, employee_email, amount, category,
                         description, manager_email
    - Valid categories : travel, meals, supplies, equipment, software, other
    - Amount < 100     : auto-approved (no manager review)
    - Amount >= 100    : wait for manager decision
    - No response in TIMEOUT_MINUTES minutes -> escalated (auto-approved)
    - Employee is always emailed with the final outcome
"""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any

import azure.functions as func
import azure.durable_functions as df

# ---------------------------------------------------------------------------
# Constants / configuration
# ---------------------------------------------------------------------------

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

AUTO_APPROVE_THRESHOLD: float = 100.0

# For local testing the timeout is kept short. In production, override via
# the APP SETTING EXPENSE_TIMEOUT_MINUTES (e.g. 4320 = 3 days).
TIMEOUT_MINUTES: int = int(os.environ.get("EXPENSE_TIMEOUT_MINUTES", "2"))

APPROVAL_EVENT_NAME: str = "ManagerDecision"

# ---------------------------------------------------------------------------
# App registration (Python v2 model)
# ---------------------------------------------------------------------------

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ===========================================================================
# CLIENT FUNCTIONS (HTTP triggers)
# ===========================================================================

@app.route(route="expenses", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_expense_workflow(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    """
    HTTP trigger that starts a new expense approval orchestration.

    POST /api/expenses
    Body: JSON expense request
    """
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = await client.start_new("expense_orchestrator", None, payload)
    logging.info("Started orchestration with ID = %s", instance_id)

    status_response = client.create_check_status_response(req, instance_id)
    # Attach our own convenience fields to the standard status response body
    body = json.loads(status_response.get_body())
    body["instanceId"] = instance_id
    body["approveUrl"] = (
        f"{req.url.split('/api/')[0]}/api/expenses/{instance_id}/approve"
    )
    body["rejectUrl"] = (
        f"{req.url.split('/api/')[0]}/api/expenses/{instance_id}/reject"
    )
    return func.HttpResponse(
        json.dumps(body),
        status_code=202,
        mimetype="application/json",
    )


@app.route(route="expenses/{instance_id}/approve", methods=["POST"])
@app.durable_client_input(client_name="client")
async def manager_approve(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    """Simulates the manager pressing 'Approve' in an email/approval UI."""
    return await _raise_manager_decision(req, client, decision="approved")


@app.route(route="expenses/{instance_id}/reject", methods=["POST"])
@app.durable_client_input(client_name="client")
async def manager_reject(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    """Simulates the manager pressing 'Reject'."""
    return await _raise_manager_decision(req, client, decision="rejected")


async def _raise_manager_decision(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    decision: str,
) -> func.HttpResponse:
    instance_id = req.route_params.get("instance_id")
    if not instance_id:
        return func.HttpResponse(
            json.dumps({"error": "instance_id is required"}),
            status_code=400,
            mimetype="application/json",
        )

    # Optional: manager can attach a comment as JSON body
    comment = ""
    try:
        body = req.get_json()
        if isinstance(body, dict):
            comment = str(body.get("comment", ""))
    except ValueError:
        pass

    await client.raise_event(
        instance_id,
        APPROVAL_EVENT_NAME,
        {"decision": decision, "comment": comment},
    )
    return func.HttpResponse(
        json.dumps(
            {
                "instanceId": instance_id,
                "eventRaised": APPROVAL_EVENT_NAME,
                "decision": decision,
            }
        ),
        status_code=202,
        mimetype="application/json",
    )


# ===========================================================================
# ORCHESTRATOR
# ===========================================================================

@app.orchestration_trigger(context_name="context")
def expense_orchestrator(context: df.DurableOrchestrationContext):
    """
    Main expense approval workflow.

    Steps:
        1. validate_expense       (activity)
        2. process_expense        (activity) - id, timestamp, status
        3. If amount >= 100  -> wait_for_manager_decision with durable timer
        4. send_notification      (activity)
    """
    payload = context.get_input() or {}

    # 1. Validation ---------------------------------------------------------
    validation_result = yield context.call_activity("validate_expense", payload)

    if not validation_result["is_valid"]:
        notification_input = {
            "expense": payload,
            "final_status": "rejected_validation",
            "reason": validation_result["errors"],
        }
        yield context.call_activity("send_notification", notification_input)
        return {
            "status": "rejected_validation",
            "errors": validation_result["errors"],
        }

    # 2. Processing (create normalized record) ------------------------------
    processed = yield context.call_activity("process_expense", payload)

    # 3. Approval decision --------------------------------------------------
    amount = float(processed["amount"])

    if amount < AUTO_APPROVE_THRESHOLD:
        final_status = "auto_approved"
        manager_comment = "Under auto-approval threshold"
        escalated = False
    else:
        # Human Interaction pattern with durable timer
        approval_event = context.wait_for_external_event(APPROVAL_EVENT_NAME)
        deadline = context.current_utc_datetime + timedelta(minutes=TIMEOUT_MINUTES)
        timeout_task = context.create_timer(deadline)

        winner = yield context.task_any([approval_event, timeout_task])

        if winner == approval_event:
            timeout_task.cancel()
            decision_payload = approval_event.result
            final_status = decision_payload.get("decision", "rejected")
            manager_comment = decision_payload.get("comment", "")
            escalated = False
        else:
            # Timer fired first -> escalate / auto-approve
            final_status = "escalated"
            manager_comment = (
                f"No manager response within {TIMEOUT_MINUTES} minute(s); "
                "auto-approved and escalated."
            )
            escalated = True

    # 4. Notify employee ----------------------------------------------------
    notification_input = {
        "expense": processed,
        "final_status": final_status,
        "reason": manager_comment,
        "escalated": escalated,
    }
    yield context.call_activity("send_notification", notification_input)

    return {
        "expenseId": processed["expense_id"],
        "status": final_status,
        "escalated": escalated,
        "comment": manager_comment,
    }


# ===========================================================================
# ACTIVITIES
# ===========================================================================

@app.activity_trigger(input_name="payload")
def validate_expense(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate required fields, types, category, and amount."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        return {"is_valid": False, "errors": ["Request body must be a JSON object"]}

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
        errors.append(
            f"category must be one of: {sorted(VALID_CATEGORIES)}"
        )

    # Very light email sanity check (no regex dependency)
    for email_field in ("employee_email", "manager_email"):
        value = payload.get(email_field)
        if value and "@" not in str(value):
            errors.append(f"{email_field} does not look like an email address")

    logging.info("Validation result: errors=%s", errors)
    return {"is_valid": len(errors) == 0, "errors": errors}


@app.activity_trigger(input_name="payload")
def process_expense(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize and enrich the expense record. Real system would persist it."""
    import uuid
    from datetime import datetime, timezone

    processed = {
        "expense_id": str(uuid.uuid4()),
        "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
        "employee_name": str(payload["employee_name"]).strip(),
        "employee_email": str(payload["employee_email"]).strip().lower(),
        "manager_email": str(payload["manager_email"]).strip().lower(),
        "amount": round(float(payload["amount"]), 2),
        "category": str(payload["category"]).lower(),
        "description": str(payload["description"]).strip(),
    }
    logging.info(
        "Processed expense %s for %s amount=%s",
        processed["expense_id"],
        processed["employee_email"],
        processed["amount"],
    )
    return processed


@app.activity_trigger(input_name="payload")
def send_notification(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Send a notification email to the employee.

    For the assignment demo this logs a mock email; in production this would
    call SendGrid, Graph API, ACS Email, or similar. Swap the body of this
    function for a real send call and add the credentials to app settings.
    """
    expense = payload.get("expense", {})
    status = payload.get("final_status", "unknown")
    reason = payload.get("reason", "")
    escalated = payload.get("escalated", False)

    subject = f"Expense {expense.get('expense_id', '[pending]')}: {status.upper()}"
    body_lines = [
        f"Hello {expense.get('employee_name', '')},",
        "",
        f"Your expense request for ${expense.get('amount', '?')} "
        f"({expense.get('category', '?')}) has been {status.upper()}.",
        "",
        f"Description: {expense.get('description', '')}",
        f"Reason/Comment: {reason}",
    ]
    if escalated:
        body_lines.append(
            "NOTE: No manager response was received within the SLA. "
            "This expense was auto-approved and escalated to Finance."
        )
    body_lines.append("")
    body_lines.append("Thank you,\nExpense Automation")

    mock_email = {
        "to": expense.get("employee_email", ""),
        "subject": subject,
        "body": "\n".join(body_lines),
    }
    logging.info("MOCK EMAIL SENT >>> %s", json.dumps(mock_email, indent=2))
    return {"sent": True, "email": mock_email}
