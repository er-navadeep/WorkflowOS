# WorkFlowOS — Autonomous Workflow Discovery, Approval & Automation

WorkFlowOS is an intelligent workflow operating system that passively observes normal user activity, detects repetitive behavioral patterns using deterministic sequence mining, synthesizes structured executable workflows using Gemini AI, requires human approval, and autonomously executes approved workflows via event-driven background triggers with built-in deduplication and human intervention checkpoints.

---

## 🔄 Official Required Lifecycle

WorkFlowOS strictly follows the official 7-stage lifecycle:

```
Observe → Understand → Detect Repetition → Generate Workflow → User Approval → Automate → Learn
```

```
[Normal User Activity]
         ↓
    1. OBSERVE
    Activity Agent captures structured semantic interaction events (Gmail, CRM, Slack)
         ↓
    2. UNDERSTAND
    Gemini AI analyzes observed sequences to determine high-level business intent ("Process Customer Request")
         ↓
    3. DETECT REPETITION
    Deterministic sequence mining identifies repeated behavioral patterns across sessions (Score >= 0.8)
         ↓
    4. GENERATE WORKFLOW
    AI synthesizes structured, multi-step workflow with inputs, outputs, conditions, and intervention guards
         ↓
    5. USER APPROVAL
    Human review guardrail: workflows remain DRAFT until explicitly approved. Unapproved workflows CANNOT run
         ↓
    6. AUTOMATE
    Event-driven background TriggerScheduler detects new events (e.g. Gmail inbox), checks idempotency, and executes
         ↓
    7. LEARN
    Feedback foundation records execution outcomes, step-level performance, and intervention metrics
```

---

## 🎯 Official Use Case: Customer Request Processing

The official canonical workflow processes inbound customer requests from Gmail to CRM with Slack notifications:

```
Trigger:
  New customer request received in Gmail (has:attachment)

Action 1:
  Read email and identify customer (Gmail / read_email)

Action 2:
  Download relevant attachment (Gmail / download_file)

Action 3:
  Find customer in CRM (CRM / find_customer)

Condition:
  If customer cannot be found in CRM:
    → STOP workflow immediately
    → Transition to NEEDS_INTERVENTION
    → Request human intervention (do NOT create fake customer, do NOT notify Slack)

Action 4:
  Update customer record with request information and attachment (CRM / update_customer)

Action 5:
  Send Slack notification to relevant team (Slack / send_message)
```

### ⚡ Automation Priority Architecture

WorkFlowOS adheres to the official automation hierarchy:
1. **API Integration** *(Preferred)*: Direct REST/OAuth APIs (Gmail API v1, Slack Webhooks, CRM API)
2. **Application Integration**: Local CLI / IPC / Structured SDKs
3. **Accessibility / Semantic UI**: OS accessibility APIs (UIAutomation)
4. **Browser Automation**: Headless browser automation (Playwright/Puppeteer)
5. **Computer Vision / UI Fallback**: Coordinate-based clicking and OCR fallback

*Note: The official Gmail/CRM/Slack pipeline uses direct API and Application Integrations for maximum determinism and reliability.*

---

## 🛠️ Prerequisites

Before running WorkFlowOS, ensure the following tools are installed:

- **Python**: Version 3.10+ (tested on Python 3.14)
- **Node.js**: Version 18+ and `npm`
- **MongoDB**: Version 6.0+ running locally on port 27017 (or MongoDB Atlas)
- **Google Gemini API Key**: For AI Workflow Understanding and Workflow Generation
- **Google Cloud OAuth 2.0 Credentials**: For Gmail API read-only operations (`https://www.googleapis.com/auth/gmail.readonly`)
- **Slack Incoming Webhook URL**: For sending team notifications

---

## 🔑 Environment Configuration

Create a `.env` file in the project root (or inside `backend/`):

```bash
# MongoDB Connection
MONGODB_URI=mongodb://127.0.0.1:27017
DATABASE_NAME=workflow_os

# Google Gemini API (AI Understanding & Generation)
GEMINI_API_KEY=your_gemini_api_key_here

# Gmail OAuth 2.0 (Read-Only API Access)
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token
GMAIL_USER_ID=me

# Slack Webhook Integration
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/XXXX

# Automation & Scheduler Settings
AUTOMATION_ENABLED=true
TRIGGER_POLL_INTERVAL_SECONDS=30
TRIGGER_MAX_EVENTS_PER_POLL=10
TRIGGER_MAX_CONCURRENT_EXECUTIONS=3

# Frontend API Target
VITE_API_URL=http://localhost:8000
```

> **Security Note**: Never commit `.env` or credentials to source control. WorkFlowOS strictly ensures zero secrets are leaked in logs, database records, API payloads, or client bundles.

---

## 📦 Installation

### 1. Backend Setup

```bash
# Navigate to project root
cd Hackthon

# Create and activate Python virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node modules
npm install

# Return to project root
cd ..
```

---

## 🚀 Running the Application

### Step 1: Start MongoDB

Ensure MongoDB is active on `localhost:27017`:

```powershell
# Windows (if running as service, it starts automatically):
# Or run manually:
mongod --dbpath "C:\data\db"
```

### Step 2: Start the FastAPI Backend

Run the backend from the project root using Uvicorn:

```powershell
uvicorn app.main:app --reload --app-dir backend
```

- **Backend API**: `http://localhost:8000`
- **Swagger Documentation**: `http://localhost:8000/docs`
- **TriggerScheduler**: Starts automatically in the background on startup (no separate polling service required).

### Step 3: Start the React Frontend

Open a new terminal window:

```powershell
cd frontend
npm run dev
```

- **Frontend Application**: `http://localhost:5173`

---

## ⚙️ How Automatic Polling Works

WorkFlowOS includes a robust, single-instance **`TriggerScheduler`** integrated directly into the FastAPI application lifecycle (`backend/app/services/trigger_scheduler.py`):

1. **Automatic Lifecycle**: When FastAPI starts, the `TriggerScheduler` starts an asynchronous background polling loop (`asyncio.create_task`).
2. **Interval Polling**: Every `TRIGGER_POLL_INTERVAL_SECONDS` (default: 30s), the scheduler polls all `ACTIVE` triggers in MongoDB.
3. **Event Detection**: The `TriggerService` queries Gmail for new matching messages (e.g. `has:attachment`).
4. **Idempotency & Checkpointing**:
   - For every detected message, a deterministic key `trigger:{workflow_id}:{messageId}` is checked in the `trigger_checkpoints` collection.
   - If already processed, the message is skipped immediately.
   - If new, an atomic reservation checkpoint is created (`STATUS=PENDING`).
5. **Execution Dispatch**: The execution engine executes the approved workflow steps live.
6. **Checkpoint Finalization**: The checkpoint is updated with `execution_id` and `STATUS=COMPLETED`.
7. **Second Poll Deduplication**: Any subsequent poll of the same message is identified as a duplicate and ignored.

---

## 🎬 Complete Hackathon Demo Walkthrough

Follow this step-by-step sequence to demonstrate the entire WorkFlowOS lifecycle to judges:

### Phase 1: User Performs Normal Work (Observe)
1. Open the UI at `http://localhost:5173` and navigate to **Activity Agent**.
2. WorkFlowOS observes user actions: reading an email in Gmail, downloading a customer PDF, looking up the customer in CRM, updating the record, and notifying the team on Slack.
3. Show the **Observed Activity Feed**: structured events captured with application, action, timestamps, and parameters.

### Phase 2: AI Understanding & Discovery (Understand & Detect Repetition)
1. Navigate to **Discovery**.
2. Click **Run Discovery**: The engine analyzes session groupings and sequence frequency.
3. Show the discovered candidate pattern:
   - Sequence: `Gmail -> read_email`, `open_email`, `download_file` → `CRM -> find_customer`, `update_customer` → `Slack -> send_message`.
   - Repetition score: `1.0` (high confidence).
4. Click **Understand Pattern**: Gemini AI explains the business intent as *"Process Customer Request"*.

### Phase 3: Workflow Generation & Human Approval (Generate & Approve)
1. Click **Generate Workflow**:
   - WorkFlowOS synthesizes the formal executable definition.
   - Shows the 5 business steps and the critical condition:
     *`If customer cannot be found in CRM → Stop & Request Human Intervention`*.
2. Navigate to **Workflows**:
   - The generated workflow is in **DRAFT** status.
   - Verify that automation is blocked while in DRAFT.
3. Click **Review & Approve**:
   - Inspector reviews steps and conditions.
   - Status transitions to **APPROVED**.

### Phase 4: Automation & Live Success Path (Automate & Execute)
1. Navigate to **Automation & Triggers**.
2. Enable the **Gmail Inbound Trigger** (`has:attachment`).
3. Send a live test email with an attachment from a registered customer (e.g., `Alice Brown / CUST-1001 / nav@example.test`).
4. Watch the `TriggerScheduler` automatically:
   - Detect the new message.
   - Create a checkpoint.
   - Dispatch live execution.
5. In **Execution History**:
   - Show execution status: **COMPLETED** (6/6 steps).
   - Step 1–3: Downloaded attachment saved to `backend/app/runtime/downloads/`.
   - Step 4: `find_customer` returned `customerFound=True`.
   - Step 5: `update_customer` updated notes and status in Mock CRM.
   - Step 6: `send_message` delivered live Slack notification.

### Phase 5: Failure / Human Intervention Path (Guardrail)
1. Send or simulate a request from an **unregistered / unknown customer** (e.g., `ghost@unknown.test`).
2. The trigger detects the event and dispatches execution:
   - Steps 1–3 succeed (email opened, attachment downloaded).
   - Step 4 (`find_customer`): Customer is **NOT FOUND** in CRM (`customerFound=False`).
   - The workflow condition evaluates: **Execution STOPS immediately**.
   - Step 5 (update CRM) is **SKIPPED** (no fake data created).
   - Step 6 (Slack notification) is **SKIPPED**.
3. In **Execution History**:
   - Status displays **NEEDS_INTERVENTION** (purple badge).
   - Modal displays human intervention guidance: *"Customer 'ghost@unknown.test' was not found in CRM. Workflow execution stopped and requires human intervention."*

### Phase 6: Deduplication & Learning Foundation (Learn)
1. The scheduler performs its next poll cycle:
   - Evaluates the inbox.
   - Identifies the processed message IDs in `trigger_checkpoints`.
   - Skips without re-executing.
2. In **Learning / Feedback**:
   - View execution success rate, step failure distributions, and intervention frequency.

---

## 🧪 Verification & Test Suite

### Run All Unit and Integration Tests

```powershell
# Run the complete test suite
pytest tests/ -v
```

### Run End-to-End Live Pipeline Verification (Parts 8 & 9)

```powershell
python scripts/verify_end_to_end_workflow.py
```
*Validates MongoDB connection, dry-run execution, live 6-step success path with CRM restoration, and live customer-not-found human intervention path.*

### Run Automatic Triggering & Deduplication Verification (Part 10 & 14)

```powershell
python scripts/verify_automatic_triggering.py
```
*Validates active trigger polling, automatic live dispatch, checkpoint creation, and second-poll deduplication.*

### Build Frontend for Production

```powershell
cd frontend
npm run build
```

---

## 🛡️ Security & Zero-Leakage Guarantee

- **Zero Credentials in Code**: All API keys, secrets, tokens, and webhooks are strictly read from environment variables.
- **Log Redaction**: Execution logs, step payloads, and error summaries scrub OAuth tokens, Authorization headers, and webhook URLs.
- **Read-Only Scopes**: Gmail integration strictly requests `https://www.googleapis.com/auth/gmail.readonly`.
- **Local Mock CRM**: Customer data is maintained in a local isolated MongoDB collection (`mock_crm_customers`) to prevent accidental external CRM modification.