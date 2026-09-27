# WorkFlowOS — Hackathon Live Demonstration Guide

## 1. Overview

This document describes the end-to-end demonstration procedure for showcasing WorkFlowOS at a hackathon, pitch, or live evaluation.

The system demonstrates the complete autonomous cycle:
```
OBSERVE → DISCOVER → UNDERSTAND → GENERATE → APPROVE → ENABLE AUTOMATION → AUTOMATIC TRIGGER → EXECUTE → AUDIT → FEEDBACK
```

---

## 2. Prerequisites & Environment Setup

Ensure the following background services are running:
1. **Local MongoDB**:
   ```bash
   mongod --dbpath <data-path>
   ```
2. **Backend Server**:
   ```bash
   cd backend
   uvicorn app.main:app --port 8000 --host 127.0.0.1
   ```
3. **Frontend Server**:
   ```bash
   cd frontend
   npm run dev
   ```
   Open `http://localhost:5173` in your browser.

4. **Environment Variables**:
   Stored safely in `.env` (never committed or printed):
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REFRESH_TOKEN`
   - `SLACK_WEBHOOK_URL`
   - `GEMINI_API_KEY`

---

## 3. Live Demo Step-by-Step Walkthrough

### Step 1: Desktop Activity Observation
1. Navigate to `/activity`.
2. Show incoming activity event streams captured from OS-level window and input actions.
3. Highlight that events are sanitized and stored in MongoDB.

### Step 2: AI Workflow Discovery
1. Navigate to `/discovery`.
2. Trigger "Run Discovery Analysis".
3. Show discovered candidate workflow clusters identified from recurring activity patterns.

### Step 3: AI Understanding & Synthesis
1. Click into a discovered candidate.
2. View the Gemini-powered semantic understanding: intent, sequential steps, variables, and failure handling conditions.
3. Show generated workflow definition.

### Step 4: Human Governance & Approval
1. Navigate to `/approvals`.
2. Inspect the pending workflow.
3. Point out the hard governance guard: unapproved workflows cannot be simulated live or automated.
4. Click **Approve Workflow**.

### Step 5: Automation Controls & Trigger Activation
1. Navigate to the workflow detail page (`/workflows/{workflow_id}`).
2. Point out the **Automation Trigger Controls** card:
   - Status: `PAUSED`
   - Source: `Gmail (customer_email_received)`
   - Polling frequency: `30 seconds`
3. Toggle the Automation switch to **ON**:
   - Status transitions to `ACTIVE` (bright emerald badge).
   - Polling scheduler begins monitoring inbox in the background.

### Step 6: Live Automatic Execution
1. Click **Poll Now** on the Trigger Control Card (or wait for the 30s background cycle).
2. The TriggerService polls Gmail (read-only), detects a new customer email message, reserves an atomic checkpoint, and invokes `execute_live()`.
3. In real-time:
   - Step 1: `Gmail / read_email` -> Finds matching customer email.
   - Step 2: `Gmail / open_email` -> Extracts sender, subject, and attachment parts.
   - Step 3: `Gmail / download_file` -> Downloads attachment into secure storage.
   - Step 4: `CRM / find_customer` -> Looks up customer in local mock CRM.
   - Step 5: `CRM / update_customer` -> Updates customer account status and notes.
   - Step 6: `Slack / send_message` -> Delivers live Slack alert to your team channel.

### Step 7: Execution History & Idempotency Audit
1. Scroll down to the **Execution History Section**:
   - Notice the purple/indigo **AUTOMATIC** badge distinguishing this run from manual runs.
   - Displays trigger metadata: Source Application (`Gmail`) and event snippet.
2. Click the execution to inspect the detail modal:
   - Full 6-step execution log with exact timestamps.
   - Live execution verification badge.
3. Click **Poll Now** again:
   - Notice that the message is immediately identified as already checkpointed.
   - Deduplication skips processing — **zero duplicate executions created**!

### Step 8: Safe Human Intervention (Optional Edge-Case Demo)
1. If an email references a customer who does not exist in the CRM, the pipeline safely stops with status:
   `needs_intervention`
2. Demonstrates safety: WorkFlowOS never hallucinates customers or performs corrupting blind updates.
