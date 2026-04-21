# CST8917 — Final Project: Expense Approval Workflow, Two Ways

| Field                         | Value                                             |
| ----------------------------- | ------------------------------------------------- |
| **Student**                   | Ahmed Boudouh                                     |
| **Student #**                 | 041162807                                         |
| **Course**                    | CST8917 — Serverless Applications                 |
| **Title**                     | Expense Approval: Durable Functions vs Logic Apps |
| **Submitted**                 | April 21, 2026                                    |
| **Video (YouTube, unlisted)** | https://youtu.be/vCR9Ds7q8iE                      |

---

## 1. Project Overview

This project implements an identical expense-approval business workflow twice,
using two very different Azure serverless orchestration styles, and compares
them across development experience, testability, error handling, human
interaction, observability, and cost.

**Business rules (identical in both versions)**

- Input fields: `employee_name`, `employee_email`, `amount`, `category`,
  `description`, `manager_email`. All are required.
- Valid categories: `travel`, `meals`, `supplies`, `equipment`, `software`,
  `other`.
- Amounts **under $100** are auto-approved without manager review.
- Amounts **≥ $100** require a manager decision.
- If the manager does not respond within the SLA timeout, the expense is
  auto-approved and flagged as **escalated**.
- The employee always receives a notification email with the final outcome.

**Repository layout**

```
CST8917-FinalProject-AhmedBoudouh/
├── README.md                             
├── .gitignore
├── test-dashboard.html                  
├── test-dashboard-version-b.html         
│
├── version-a-durable-functions/         
│   ├── function_app.py                   
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.example.json
│   ├── test-durable.http                
│   └── DEPLOYMENT.md
│
├── version-b-logic-apps/                 
│   ├── function_app.py                   
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.example.json
│   ├── logic-app-workflow.json          
│   ├── test-expense.http                 
│   ├── DEPLOYMENT.md
│   └── screenshots/                      
└── presentation/
    ├── slides.pptx                       
    ├── video-link.md                    
    └── video-script.md                   
```

### Test dashboards (shortcut for graders)

Two single-file HTML dashboards are included at the repository root so the
scenarios can be exercised without installing anything:

- **`test-dashboard.html`** — calls the deployed Version A Function App over
  HTTP, polls the Durable Functions status endpoint, and renders each
  scenario's final state with a colored badge. It is the cleanest way to
  watch all six scenarios run in parallel. (CORS must be enabled on the
  Function App — one-time setup documented in the dashboard's header.)
- **`test-dashboard-version-b.html`** — Service Bus has no browser-accessible
  REST API (no CORS, SAS auth required), so this dashboard is *guided*: each
  scenario has a **Copy JSON** button and a short instruction for pasting it
  into Azure Service Bus Explorer. It also contains the three topic-pub/sub
  test messages used to demonstrate correlation-filtered subscriptions.

Both dashboards match the scenario set in the `test-*.http` files and are
what the submission video demonstrates on screen.

---

## 2. Version A — Azure Durable Functions (Python v2)

### Architecture

```
HTTP (POST /api/expenses) ──► Client Function
                                   │
                                   ▼
                          Orchestrator function
                            │        │        │
                            ▼        ▼        ▼
                      validate   process   send_notification
                      _expense   _expense
                                   │
                        amount ≥ $100 only
                                   ▼
                     wait_for_external_event("ManagerDecision")
                            ┌──────────┴──────────┐
                            ▼                     ▼
                      external event        durable timer
                     (/approve /reject)       (TIMEOUT_MINUTES)
```

The orchestrator demonstrates all four required patterns: **client**,
**activity chaining** (`validate_expense → process_expense → send_notification`),
**Human Interaction** (`wait_for_external_event` racing a `create_timer`), and
two additional **HTTP client routes** (`/approve`, `/reject`) that raise the
external event — simulating a manager clicking a button in a real UI.

### Deployed endpoints

| Route                                          | Method | Purpose                                                      |
| ---------------------------------------------- | ------ | ------------------------------------------------------------ |
| `/api/expenses`                                | POST   | Start a new expense orchestration                            |
| `/api/expenses/{instance_id}/approve`          | POST   | Simulate manager Approve click                               |
| `/api/expenses/{instance_id}/reject`           | POST   | Simulate manager Reject click                                |
| `/runtime/webhooks/durabletask/instances/{id}` | GET    | Inspect orchestration status (built-in Durable Task webhook) |

Auth level: `ANONYMOUS` (so the dashboard and `test-durable.http` can call
them without a function key). In production this would be raised to
`FUNCTION` or secured behind APIM.

### Design decisions

- **Python v2 programming model with `DFApp`.** Single-file, decorator-driven
  registration keeps the code readable and avoids the legacy per-function
  folders of the v1 model.
- **`task_any([event, timer])` rather than `create_timer` in a `try/except`.**
  More explicit about what is racing, easier to reason about in replay.
- **Auto-approval is decided in the orchestrator, not in the validator.** The
  validator only checks *shape*; business thresholds live in the orchestration
  so they can be changed without touching validation rules.
- **`EXPENSE_TIMEOUT_MINUTES` app setting** (default 2) so the escalation
  path can be demoed in a few minutes during recording while production can
  use 72 hours.
- **Stable `expense_id` generated once in `process_expense`** so every later
  activity (and the employee notification) references the same id even on
  replay.

### Challenges I hit

- **Deterministic replay:** I initially used `datetime.utcnow()` inside the
  orchestrator, which triggers a replay warning. Moved anything time-related
  to `context.current_utc_datetime` / activities.
- **Local dev needs Azurite.** The Durable hub stores state in Azure Storage;
  without Azurite running, orchestrations start but never progress.
- **Event names are case-sensitive.** `ManagerDecision` must match exactly
  between the raise site and the orchestrator, or the timer always wins.

---

## 3. Version B — Azure Logic Apps + Service Bus

### Reference architecture (documented design)

```
Publisher → Service Bus queue: expense-requests
              │
              ▼
       Logic App  ExpenseApproval
              ├─ Parse JSON
              ├─ Call validator Azure Function (function_app.py)
              ├─ If invalid  ────────────► (emit outcome)
              ├─ If amount < $100 ────────► (emit outcome: auto-approved)
              └─ Else  Outlook "Send approval email"
                        (Send-approval-email webhook, 2-minute timeout)
                        ├─ Approve  → (emit outcome: approved)
                        ├─ Reject   → (emit outcome: rejected)
                        └─ TimedOut → (emit outcome: escalated)

Service Bus topic: expense-outcomes
  ├─ Subscription expense-approved    (filter: status='approved')
  ├─ Subscription expense-rejected    (filter: status='rejected')
  ├─ Subscription expense-escalated   (filter: status='escalated')
  └─ Subscription all-outcomes        (no filter)
```

### Delivered implementation

The Logic App was built in the **Azure Portal designer**, not from a JSON
template. `version-b-logic-apps/logic-app-workflow.json` is the **reference
design** committed as a working artifact; the live workflow in the tenant
was constructed action-by-action in the visual designer. This choice is in
scope for Logic Apps — the whole point of a declarative service is that
you author it in the designer — and the comparison section below discusses
the developer-experience implications.

The live `ExpenseApproval` Logic App simplifies the reference design on
two points for practical reasons that surfaced during implementation in
the CloudLabs-provisioned Azure tenant:

1. **Outcome notifications are sent directly from `ExpenseApproval`**
   using five `Send an email (V2)` actions (one per terminal state:
   auto-approved, approved, rejected, escalated, validation-rejected),
   instead of publishing to `expense-outcomes` and letting a second
   `NotifyEmployee` Logic App consume and fan-out. The topic and its four
   filtered subscriptions still exist (provisioned and verified — see
   §3.3 below), and are demonstrated end-to-end with three manually
   sent messages. Functionally the five terminal branches fire; they
   just call the Outlook connector instead of the Service Bus publish
   connector. The reduction to one Logic App was made after the
   designer repeatedly failed to hydrate swagger metadata for
   code-view-pasted Service Bus publish actions ("Unable to initialize
   operation" / "Incomplete information for operation"), a known class
   of issue with Consumption Logic Apps when publish actions are
   code-view-authored rather than designer-authored.

2. **Approve/Reject actionable-message buttons** are only demonstrated
   via the escalation (Default / timeout) branch. The Outlook
   `Send approval email` webhook is wired with `limit.timeout: PT2M`
   and a `Switch` on `SelectedOption`, but Microsoft's Actionable Message
   policy renders those buttons only when the email sender and recipient
   are inside the same O365 tenant. The CloudLabs tenant
   (`odl_user_…@cloudlabsai.com`) is disposable and its mailbox is not
   accessible to students, so clicking Approve/Reject from outside that
   tenant is not possible in this environment. The Default branch of the
   `Switch` is demonstrated end-to-end (scenario 4 of the run history),
   which functionally proves that the webhook subscribed and then timed
   out — a path that is only reachable if Approve/Reject would otherwise
   be reachable when the actionable-message policy allows.

### Scenarios demonstrated end-to-end

| #   | Scenario                              | Delivered                                                                          |
| --- | ------------------------------------- | ---------------------------------------------------------------------------------- |
| 1   | Auto-approve (amount < $100)          | ✅ inbox email received, green run in history                                       |
| 2   | Manager approves (amount ≥ $100)      | ⚠️  code path present, button click not executable cross-tenant                     |
| 3   | Manager rejects                       | ⚠️  same as above                                                                   |
| 4   | No response → escalated (2-min timer) | ✅ inbox email received, green run in history, Default branch of Switch highlighted |
| 5   | Validation error (invalid category)   | ✅ inbox email with validator error list, False branch highlighted                  |

### 3.3 Filtered subscriptions — demonstrated live

To prove the pub/sub requirement independently of the Logic App, three
messages are sent directly to `expense-outcomes` with the custom property
`status` set to `approved`, `rejected`, and `escalated` respectively. Peeking
each subscription shows that:

| Subscription        | Filter                 | Messages visible          |
| ------------------- | ---------------------- | ------------------------- |
| `expense-approved`  | `status = 'approved'`  | 1 (only status=approved)  |
| `expense-rejected`  | `status = 'rejected'`  | 1 (only status=rejected)  |
| `expense-escalated` | `status = 'escalated'` | 1 (only status=escalated) |
| `all-outcomes`      | (none)                 | 3 (all three)             |

Screenshots of each peek are in `version-b-logic-apps/screenshots/`. The
Version B test dashboard (`test-dashboard-version-b.html`) contains the
three pre-formatted JSON bodies plus the custom-property values to copy
into Service Bus Explorer.

### Design decisions

- **Service Bus queue for ingress** so producers can publish fire-and-forget
  and the Logic App can back-pressure if needed.
- **Single validator Function, not one per rule.** The rule set is tiny and
  cohesive; splitting would multiply cold-start cost without any observability
  benefit.
- **Manager approval via the Outlook `Send approval email` webhook** with a
  two-minute timeout and a `Switch` on `SelectedOption`. This connector is
  first-class, has built-in timeout semantics, and cleanly surfaces
  `Approve`, `Reject`, and `TimedOut` as discrete cases. Trade-off: it
  requires an O365 mailbox; a multi-tenant SaaS would instead use
  `listCallbackUrl()` + a web UI.
- **Topic with correlation-filter subscriptions** on a custom
  `status` message property, so each downstream concern can be wired
  independently without the producer knowing who listens.

---

## 4. Comparison Analysis

Both versions satisfy identical business requirements, but the experience of
building, testing, operating, and costing them is very different. I evaluate
the two along the six dimensions required by the assignment.

### 4.1 Development Experience

Durable Functions felt faster once the skeleton was in place. Because the
orchestrator is ordinary Python, I could keep the entire workflow in one file,
use language features like `if/else`, `float()`, and list literals, and lean
on my IDE for autocomplete and type hints. Refactoring was cheap: renaming
`wait_for_manager_decision` to `ManagerDecision` is a two-click operation.
Logic Apps gave me a faster start — the designer's triggers, connectors, and
managed identities are genuinely impressive — but as soon as I needed
non-trivial branching (valid vs invalid, under vs over $100, Approve vs
Reject vs TimedOut) the visual surface became cluttered, and a lot of my
"code" ended up as Workflow Definition Language expressions like
`@coalesce(body('…')?['SelectedOption'], 'TimedOut')`, which are awkward to
write and impossible to unit test. Confidence in correctness was higher in
Version A because I could read the whole orchestrator top-to-bottom.

### 4.2 Testability

Version A is straightforwardly testable. The HTTP start endpoint and the
approve/reject endpoints can be driven by `test-durable.http` or by the
HTML dashboard included in the repo. Individual activities are pure functions
that take JSON and return JSON, so they are trivially unit-testable with
`pytest`. Orchestrators themselves are harder (they need the Durable Task
test harness), but activity coverage catches most bugs. Version B is the
opposite: the validator Function is equally testable, but the Logic App
itself cannot really be unit-tested — you must deploy it and exercise it
through real Service Bus messages. Logic Apps does offer "Resubmit" and
inputs/outputs inspection on every run, which partially compensates, but
there is no local `func start` equivalent that fully simulates the designer.

### 4.3 Error Handling

Durable Functions gives fine-grained control: every `call_activity` can take
a `RetryOptions` object, exceptions propagate back to the orchestrator, and I
can `try/except` around specific activities. The cost is that I have to think
about this explicitly. Logic Apps gives good defaults almost for free — every
action has a per-action **Retry policy** (default exponential, 4 tries) and a
**Run after** setting that lets me wire explicit "on failure" branches. For
standard retryable flakiness the Logic Apps default is probably better than
what I would hand-roll. For bespoke logic (e.g. retry only on HTTP 429 with
jittered backoff) Durable Functions wins.

### 4.4 Human Interaction Pattern

This is where the two approaches diverge the most. Durable Functions has a
native primitive (`wait_for_external_event`) designed exactly for this: the
orchestration dehydrates, costs nothing while it waits, and resumes when the
event arrives. Racing the event against a `create_timer` is a two-line
pattern and is part of the product's official documentation. Logic Apps has
no equivalent primitive. The closest options are the Outlook approval
connector used here (which works, but ties you to a mailbox and to
Microsoft's actionable-message tenant rules), or a `Request`-trigger
callback URL paired with a separate Logic App, which effectively rebuilds
half of Durable Functions by hand. For a pure human-in-the-loop workflow,
Durable Functions is the better tool.

### 4.5 Observability

Both versions integrate with Application Insights, but the defaults are
better in Logic Apps. Every Logic App run has a graphical run history with
inputs, outputs, duration, and retry count for every action — the grader can
literally watch scenario 4's "TimedOut → Escalated" play out in the portal.
Durable Functions surfaces the same information as orchestration instances
(via `runtime/webhooks/durabletask/instances`) but the default view is a
plain JSON blob; you get real insight only after wiring Application Insights
queries or installing the VS Code Durable Task extension.

### 4.6 Cost Estimation

Using the Azure Pricing Calculator (Canada Central, April 2026 retail):

| Volume         | Version A (Durable)                                                                                 | Version B (Logic Apps)                                                                   |
| -------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **100/day**    | ~$0 Functions (within free grant) + ~$0.02 storage ≈ **~$0.15 /mo**                                 | 100 × ~7 actions × 30 days ≈ 21 000 actions × $0.000025 + SB Std $9.81 ≈ **~$10.35 /mo** |
| **10 000/day** | 300 000 executions × $0.20/1M + ~5 s avg × 128 MB memory × $0.000016/GB-s + storage ≈ **~$5-8 /mo** | 10 000 × 7 × 30 = 2.1 M actions × $0.000025 + SB Std $9.81 ≈ **~$62 /mo**                |

(Calculator rows: "Azure Functions - Consumption", "Azure Storage",
"Azure Logic Apps - Consumption", "Azure Service Bus - Standard".)

Durable Functions wins by a wide margin at scale because per-action pricing
on Logic Apps Consumption is deceptively expensive once a workflow has many
steps. Logic Apps Standard (dedicated) flips the comparison for very large
sustained volumes, but then Durable Functions Premium also enters the chat.
A subtle second-order cost is developer time: the Logic Apps estimate above
ignores that every one of those 7 actions needs a managed API connection
that must be authorized, monitored, and rotated; every connection is another
resource in the bill and another thing to break a production release.
Durable Functions, by contrast, uses only storage and outbound HTTP/SDK
calls, so the operational surface area stays small as volume grows.

### 4.7 Summary scoreboard

| Dimension                 | Winner            | Margin                                         |
| ------------------------- | ----------------- | ---------------------------------------------- |
| Development experience    | Durable Functions | moderate — faster *after* skeleton is in place |
| Integration / connectors  | Logic Apps        | large — 1000+ built-in connectors              |
| Testability               | Durable Functions | large — real local `func start`, unit tests    |
| Error handling (defaults) | Logic Apps        | small — per-action retry is free               |
| Error handling (custom)   | Durable Functions | moderate — full language power                 |
| Human Interaction pattern | Durable Functions | large — native primitive                       |
| Observability             | Logic Apps        | moderate — run history UI out of the box       |
| Cost at 100/day           | Durable Functions | ~67× cheaper ($0.15 vs $10.35)                 |
| Cost at 10 000/day        | Durable Functions | ~8× cheaper ($8 vs $62)                        |

---

## 5. Recommendation

For the specific pattern in this assignment — human-in-the-loop expense
approval with a strict cost target and a testable code trail — I would ship
**Version A (Durable Functions)** to production. It is 6-8× cheaper at
10 000/day, natively expresses the "wait for human or timeout" pattern, and
leaves the whole workflow in a single reviewable Python file that my team
can diff, code-review, unit-test, and version control like any other service.

I would reach for **Version B (Logic Apps)** in three scenarios. First, when
the workflow is dominated by *integration* rather than *logic* — e.g. "when
a new row appears in SharePoint, create a Jira ticket, post to Teams, and
append to an Excel file" — because Logic Apps' connector catalogue is
unbeatable and writing that in Functions would just be me re-implementing
connectors badly. Second, when the primary owner is a citizen developer or
business analyst rather than a software engineer, because the designer is
genuinely approachable. Third, for one-off internal automations where
observability matters more than cost because the built-in run-history UI
saves hours of debugging per incident.

The realistic hybrid — and what I would actually build at work — is a thin
Logic App at the edge (to harvest the connector ecosystem and the free
run-history telemetry) calling into Durable Functions for any non-trivial
orchestration, approval waits, or high-volume hot paths. That way each tool
is used where it is strongest and neither is stretched past its sweet spot.

---

## 6. How to Run / Reproduce

### 6.1 Version A — from scratch

```bash
cd version-a-durable-functions
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp local.settings.example.json local.settings.json

# Terminal 2
azurite --silent --location .azurite

# Terminal 1
func start
# HTTP trigger now at http://localhost:7071/api/expenses
```

Use `test-durable.http` (VS Code REST Client) or `test-dashboard.html` to
run the six scenarios. Deploy with
`func azure functionapp publish <your-app-name> --python`. Full details in
`version-a-durable-functions/DEPLOYMENT.md`.

### 6.2 Version B — from scratch

1. Create Service Bus namespace (Standard SKU — required for topics).
2. Create queue `expense-requests`.
3. Create topic `expense-outcomes` with subscriptions `expense-approved`,
   `expense-rejected`, `expense-escalated`, `all-outcomes` — and a SQL
   filter on each (except `all-outcomes`).
4. Deploy the validator Azure Function:
   `cd version-b-logic-apps && func azure functionapp publish <validator-app> --python`.
5. Create a Consumption Logic App and build the workflow in the designer
   (trigger on the queue, call the validator, branch, etc.). Reference
   the JSON in `logic-app-workflow.json` for the exact expression strings
   and action names.
6. Run the scenarios by sending JSON payloads to `expense-requests` via
   the Service Bus Explorer in the Azure Portal. The included
   `test-dashboard-version-b.html` provides ready-to-copy payloads.

Full details in `version-b-logic-apps/DEPLOYMENT.md`.

---

## 7. References

- Microsoft, *Durable Functions Overview*
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview
- Microsoft, *Human interaction pattern (Durable Functions)*
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview?tabs=csharp#human
- Microsoft, *Python v2 programming model for Azure Functions*
  https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python
- Microsoft, *Azure Logic Apps documentation*
  https://learn.microsoft.com/en-us/azure/logic-apps/
- Microsoft, *Send approval emails and wait for a reply (Outlook connector)*
  https://learn.microsoft.com/en-us/connectors/office365/#send-approval-email
- Microsoft, *Azure Service Bus — topic filters and actions*
  https://learn.microsoft.com/en-us/azure/service-bus-messaging/topic-filters
- Microsoft, *Actionable messages in Outlook — tenant requirements*
  https://learn.microsoft.com/en-us/outlook/actionable-messages/
- Microsoft, *Azure Pricing Calculator*
  https://azure.microsoft.com/en-ca/pricing/calculator/
- Ramy Mohamed, *CST8917 - 26W Final Assignment brief*
  https://github.com/ramymohamed10/26W_CST8917_Final_Assignment

---

## 8. AI Disclosure

In line with the course policy and Algonquin College's academic integrity
rules, I disclose the following use of AI tools while completing this
assignment:

- **Tool used:** Claude (Anthropic), via the Cowork assistant.
- **How it was used:**

  - Proof-reading the comparison analysis for clarity and structure.
  - Drafting the cost-estimation table which I then cross-checked against
    the Azure Pricing Calculator myself.
  - Generating the two single-file HTML test dashboards.
- **What remained my own work:** All architectural decisions (choosing the
  Outlook approval connector, choosing correlation filters over SQL filters,
  choosing a stable `expense_id` at process time, deciding to collapse the
  second Logic App in the delivered implementation), the business-rule logic
  inside the orchestrator and validator, the test scenarios, the live
  Azure provisioning work, and the final edits to every file in this
  repository.
- **Nothing was pasted unreviewed.** Every code path and sentence in this
  submission has been read, modified, and accepted by me.
