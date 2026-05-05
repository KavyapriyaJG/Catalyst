DUMMY_PRD_TEXT = """## 1. Executive Summary

This PRD defines an enterprise integration pattern for enabling legacy COBOL/CICS applications to consume external REST APIs via IBM z/OS Connect EE API Requester. [CONFIRMED]  
The sample domain is health insurance claim validation, where claim data is sent to an external rules API that returns one of three outcomes: **ACCEPTED, REJECTED, PENDING_REVIEW**. [CONFIRMED]

Business intent is to modernize mainframe workloads without rewriting core COBOL business logic by externalizing HTTP/JSON handling and centralizing API governance/security in z/OS Connect. [CONFIRMED]

This document is implementation-ready for the integration pattern and runtime/deployment behavior present in the source; where business-domain specifics are not provided by source (for example, detailed payer adjudication logic), requirements are explicitly marked. [INFERRED]

---

## 2. System Overview

### 2.1 Business Domain & Problem
- Domain: health insurance claim processing/validation integration. [CONFIRMED]
- Problem: COBOL applications should not directly implement HTTP/JSON integration logic for REST consumption. [CONFIRMED]

### 2.2 Proposed Solution
- A user triggers a CICS transaction that executes a COBOL program. [CONFIRMED]
- COBOL sends structured data (COMMAREA/container) to z/OS Connect API Requester. [CONFIRMED]
- z/OS Connect transforms COBOL ⇄ JSON, invokes outbound REST API, and maps response back to COBOL structure. [CONFIRMED]
- Secure communication and centralized authn/authz are handled at z/OS Connect layer. [CONFIRMED]

### 2.3 Stakeholders
- Mainframe application developers and CICS engineers. [CONFIRMED]
- Enterprise integration/API platform teams (z/OS Connect administrators). [CONFIRMED]
- QA and release engineering teams for deployment pipeline and runtime validation. [INFERRED]
- Security/compliance stakeholders for governance controls. [INFERRED]

### 2.4 Explicit Assumptions
- z/OS Connect EE is installed and configured. [CONFIRMED]
- CICS region is active and accessible. [CONFIRMED]
- External REST API is available and stable. [CONFIRMED]
- Copybooks map request/response structures correctly. [CONFIRMED]
- `server.xml` is the z/OS Connect configuration file used for endpoint and CICS connection configuration. [CONFIRMED]

### 2.5 Scope Boundary
- In scope: integration pattern, runtime flow, deployment artifacts/steps, and governance pattern. [CONFIRMED]
- Out of scope: external claim decision internals beyond documented inputs (claim type, amount) and outcomes. [CONFIRMED]

---

## 3. Functional Requirements

### FR-100 Claim Validation Invocation

**FR-101 Transaction Trigger and Request Initiation**  
**Requirement:** The system shall initiate an outbound claim validation API invocation when a configured CICS transaction is executed. [CONFIRMED]  
- **Input:** CICS transaction trigger + COBOL claim request structure (COMMAREA/container). [CONFIRMED]  
- **Processing:** COBOL program prepares request and calls API Requester interface. [CONFIRMED]  
- **Output:** Outbound REST request is issued through z/OS Connect. [CONFIRMED]  
- **Acceptance Criteria:**  
  1) Given a configured transaction ID and valid request payload, z/OS Connect receives an invocation request from COBOL. [INFERRED]  
  2) Invocation path uses API Requester (not custom HTTP code in COBOL). [CONFIRMED]  
  3) Invocation attempt is logged with correlation ID and timestamp. [INFERRED]

**FR-102 Data Transformation and API Invocation**  
**Requirement:** The system shall transform COBOL request structures to JSON, execute REST invocation, and transform JSON response to COBOL response structures via API Requester mapping definitions. [CONFIRMED]  
- **Input:** Copybook-defined request/response structures + API Requester archive (`.ara`). [CONFIRMED]  
- **Processing:** COBOL→JSON mapping, HTTP call, JSON→COBOL mapping. [CONFIRMED]  
- **Output:** Populated COBOL response structure returned to caller program/transaction. [CONFIRMED]  
- **Acceptance Criteria:**  
  1) No manual JSON parse/serialization logic exists in COBOL source for this flow. [CONFIRMED]  
  2) API Requester mapping executes without structural mapping error for valid payloads. [INFERRED]  
  3) For successful external response, mapped decision value is present in response structure. [INFERRED]

**FR-103 Decision Outcome Handling**  
**Requirement:** The system shall return external decision outcomes using canonical values `ACCEPTED`, `REJECTED`, `PENDING_REVIEW`. [CONFIRMED]  
- **Input:** `claimType`, `claimAmount` fields from claim request. [CONFIRMED]  
- **Processing:** External rules API evaluates and returns decision. [CONFIRMED]  
- **Output:** COBOL response contains canonical decision status. [INFERRED]  
- **Acceptance Criteria:**  
  1) Decision terminology is standardized to `PENDING_REVIEW` (not “Manual Review” in runtime payload model). [INFERRED]  
  2) Exactly one terminal decision value is returned per request. [INFERRED]

### FR-200 Validation, Errors, and Recovery

**FR-201 Input Validation at COBOL Boundary**  
**Requirement:** The system shall validate minimum request presence and format before invoking API Requester. [INFERRED]  
- **Input:** Incoming claim request structure. [CONFIRMED]  
- **Processing:** Required-field checks for `claimType`, `claimAmount`; numeric-format check for amount. [INFERRED]  
- **Output:** Either validated request or local validation error returned to caller. [INFERRED]  
- **Acceptance Criteria:**  
  1) Missing `claimType` or `claimAmount` causes no outbound API call. [INFERRED]  
  2) Validation failure returns deterministic local error code to transaction flow. [INFERRED]

**FR-202 Timeout and Retry Behavior**  
**Requirement:** The system shall enforce outbound timeout and bounded retry for transient failures. [INFERRED]  
- **Input:** Outbound invocation request. [CONFIRMED]  
- **Processing:** Timeout at 30s/request; up to 2 retries for timeout/5xx with exponential backoff (1s, 2s). [INFERRED]  
- **Output:** Success response or final integration failure status. [INFERRED]  
- **Acceptance Criteria:**  
  1) Total attempts per request do not exceed 3. [INFERRED]  
  2) Non-retryable 4xx responses are not retried. [INFERRED]

**FR-203 Fallback Decision on Integration Failure**  
**Requirement:** The system shall return `PENDING_REVIEW` when external decision cannot be obtained due to integration/runtime failure after retries. [INFERRED]  
- **Input:** Failed invocation outcome. [INFERRED]  
- **Processing:** Map failure to fallback decision and integration error metadata. [INFERRED]  
- **Output:** COBOL response includes `PENDING_REVIEW` and error reason code. [INFERRED]  
- **Acceptance Criteria:**  
  1) Timeout/network/unavailable scenarios result in fallback decision. [INFERRED]  
  2) Fallback is auditable with correlation ID and failure classification. [INFERRED]

### FR-300 Deployment and Operations

**FR-301 Build and Deployment Sequence**  
**Requirement:** The system shall support deployment via the defined sequence: COBOL compile via JCL, VSAM setup, CICS resource definition, `.ara` deployment, and `server.xml` configuration. [CONFIRMED]  
- **Input:** `.cbl`, `.cpy`, `.jcl`, `.ara`, `.aar`, `.sar`, configuration values. [CONFIRMED]  
- **Processing:** Execute deployment jobs and server configuration updates. [CONFIRMED]  
- **Output:** Runnable CICS + z/OS Connect integration endpoint and requester configuration. [INFERRED]  
- **Acceptance Criteria:**  
  1) COBOL compilation completes with return code within release standard threshold. [INFERRED]  
  2) CICS transaction executes without ABEND for valid request. [INFERRED]  
  3) Outbound call reaches external API via z/OS Connect path. [INFERRED]  
  4) Response mapping returns decision value to COBOL caller. [INFERRED]

**FR-302 Security Control Enforcement**  
**Requirement:** The system shall enforce centralized authentication/authorization for outbound API communication through z/OS Connect. [CONFIRMED]  
- **Input:** Outbound request from COBOL. [CONFIRMED]  
- **Processing:** Apply z/OS Connect-managed security policy and credentials. [CONFIRMED]  
- **Output:** Authorized secure call or denied request. [INFERRED]  
- **Acceptance Criteria:**  
  1) Unauthorized/invalid credentials are rejected before external invocation. [INFERRED]  
  2) Authorized calls succeed under configured policy. [INFERRED]

---

## 4. Data Model

### 4.1 Logical Entities

1. **ClaimRequest** [CONFIRMED]  
   - `claimType` : string (source type/length in copybook) [CONFIRMED]  
   - `claimAmount` : decimal/number (source precision/scale in copybook) [CONFIRMED]  
   - `claimId` : string [UNKNOWN]  
   - Primary Key: `claimId` [INFERRED]

2. **ClaimDecisionResponse** [CONFIRMED]  
   - `decisionStatus` : enum {`ACCEPTED`,`REJECTED`,`PENDING_REVIEW`} [CONFIRMED]  
   - `decisionReasonCode` : string [INFERRED]  
   - `correlationId` : string [INFERRED]  
   - `processingTimestamp` : datetime [INFERRED]

3. **CobolRequestStructure** (COMMAREA/container) [CONFIRMED]  
   - Backed by `.cpy` copybook fields [CONFIRMED]  
   - Field-level PIC clauses and lengths [UNKNOWN]

4. **CobolResponseStructure** [CONFIRMED]  
   - Backed by `.cpy` copybook fields [CONFIRMED]  
   - Includes decision field mapped from external API response [INFERRED]

5. **APIRequesterDefinition** (`.ara`) [CONFIRMED]  
   - Request/response mapping metadata [CONFIRMED]  
   - Endpoint binding and invocation details [INFERRED]

6. **AuditEvent** [INFERRED]  
   - `eventId` string, `claimId` string, `transactionId` string, `userId` string, `decisionStatus` enum, `apiLatencyMs` integer, `timestamp` datetime, `resultCode` string [INFERRED]

### 4.2 Relationships
- `ClaimRequest (1)` → `(1) ClaimDecisionResponse` per invocation. [INFERRED]  
- `CobolRequestStructure` maps to `ClaimRequest` through `.ara`. [CONFIRMED]  
- `ClaimDecisionResponse` maps to `CobolResponseStructure` through `.ara`. [CONFIRMED]  
- `ClaimRequest/Response` produce `AuditEvent (1..n)` records over lifecycle. [INFERRED]

### 4.3 Canonical Enumerations
- `decisionStatus`: `ACCEPTED`, `REJECTED`, `PENDING_REVIEW`. [CONFIRMED]

---

## 5. Process Flows

### 5.1 Primary Success Flow
1. User executes CICS transaction. [CONFIRMED]  
2. COBOL prepares COMMAREA/container payload. [CONFIRMED]  
3. Request sent to z/OS Connect API Requester. [CONFIRMED]  
4. z/OS Connect transforms COBOL payload to JSON. [CONFIRMED]  
5. z/OS Connect invokes external REST claim rules API. [CONFIRMED]  
6. JSON response received. [CONFIRMED]  
7. z/OS Connect maps JSON response to COBOL response structure. [CONFIRMED]  
8. COBOL receives and returns result to transaction/user. [CONFIRMED]

### 5.2 Error and Recovery Flows
- **E1 Timeout / API unavailable**: Apply timeout + retry policy; on exhaustion return `PENDING_REVIEW` with integration error metadata. [INFERRED]  
- **E2 Malformed response / mapping failure**: Fail mapping, classify error, return `PENDING_REVIEW` and log mapping failure details. [INFERRED]  
- **E3 Authorization failure**: Reject call per z/OS Connect security policy, no external success path, return integration error. [INFERRED]  
- **E4 Local input validation failure**: Do not invoke external API; return deterministic validation error to CICS caller. [INFERRED]

### 5.3 Deployment Verification Flow
1. Execute JCL compile/deploy jobs. [CONFIRMED]  
2. Provision VSAM dataset and CICS resources. [CONFIRMED]  
3. Deploy `.ara` and configure `server.xml`. [CONFIRMED]  
4. Run smoke transaction with valid payload. [INFERRED]  
5. Verify outbound call path, decision mapping, and audit log creation. [INFERRED]

---

## 6. Business Rules

**BR-001 External Decision Authority**  
- **Statement:** Claim decision is determined by external claim rules API using claim type and claim amount. [CONFIRMED]  
- **Type:** Decisioning delegation.  
- **Verification:** Integration test with valid request; confirm decision sourced from API response. [INFERRED]  
- **Traceability:** External System Interaction section in source transcript.

**BR-002 Allowed Decision Values**  
- **Statement:** Allowed decision outcomes are `ACCEPTED`, `REJECTED`, `PENDING_REVIEW`. [CONFIRMED]  
- **Type:** Enumeration constraint.  
- **Verification:** Contract test asserting response value in allowed enum set. [INFERRED]  
- **Traceability:** Transcript lists Accept/Reject/Pending review and Accept/Reject/Manual Review; standardized here to `PENDING_REVIEW`. [CONFIRMED]

**BR-003 No Direct HTTP/JSON in COBOL**  
- **Statement:** COBOL business programs shall not directly implement HTTP transport or JSON parsing for this integration. [CONFIRMED]  
- **Type:** Architectural constraint.  
- **Verification:** Code inspection + build-time static check. [INFERED]  
- **Traceability:** “No manual JSON handling is required in COBOL.”

**BR-004 Mapping via Copybooks and API Requester Metadata**  
- **Statement:** Request/response mappings shall be defined by copybooks and `.ara` metadata. [CONFIRMED]  
- **Type:** Integration contract.  
- **Verification:** Deployment artifact validation + runtime mapping test. [INFERRED]  
- **Traceability:** Components and API Requester description in source.

**BR-005 Required Deployment Steps**  
- **Statement:** Deployment must execute compile JCL, VSAM setup, CICS resource definition, `.ara` deployment, and `server.xml` configuration. [CONFIRMED]  
- **Type:** Operational rule.  
- **Verification:** Release checklist and smoke test completion. [INFERRED]  
- **Traceability:** Deployment model transcript.

**BR-006 Fallback Decision on Unresolved Integration Failure**  
- **Statement:** If external decision is unavailable after retry policy, system returns `PENDING_REVIEW`. [INFERRED]  
- **Type:** Resilience rule.  
- **Verification:** Failure-injection test (timeout/unavailable) with expected fallback response. [INFERRED]  
- **Traceability:** Error handling abstraction + enterprise operational requirement. [INFERRED]

---

## 7. External Interfaces

### 7.1 CICS/COBOL ↔ z/OS Connect API Requester
- **Direction:** Internal mainframe invocation. [CONFIRMED]  
- **Payload:** COMMAREA/container structures defined by copybooks. [CONFIRMED]  
- **Contract Artifacts:** `.cpy`, `.ara`. [CONFIRMED]

### 7.2 z/OS Connect ↔ External Claim Rules REST API
- **Direction:** Outbound from z/OS Connect. [CONFIRMED]  
- **Protocol:** HTTP/REST. [CONFIRMED]  
- **Data format:** JSON request/response. [CONFIRMED]  
- **Endpoint configuration:** `server.xml` in z/OS Connect. [CONFIRMED]  
- **Auth mechanism:** centralized authn/authz via z/OS Connect; protocol specifics not provided in source. [CONFIRMED]/[UNKNOWN]

### 7.3 Deployment/Packaging Interfaces
- `.cbl` COBOL source, `.cpy` copybooks, `.jcl` jobs, `.ara` API requester archive, `.aar/.sar` API/service archives. [CONFIRMED]

---

## 8. Non-Functional Requirements

**NFR-001 Performance**  
- p95 end-to-end response time for successful decision flow shall be ≤ 2.0 seconds under nominal load. [INFERRED]  
- p99 shall be ≤ 5.0 seconds. [INFERRED]

**NFR-002 Throughput & Scalability**  
- System shall support sustained 100 TPS and burst 150 TPS for 15 minutes without error rate breach. [INFERRED]  
- Error rate under nominal load shall remain <1%. [INFERRED]

**NFR-003 Availability & Reliability**  
- Integration service availability target shall be 99.9% monthly (excluding approved maintenance). [INFERRED]  
- Mean time to recover (MTTR) for critical integration outage shall be ≤ 60 minutes. [INFERRED]

**NFR-004 Security**  
- All outbound API traffic shall use TLS 1.2+ in transit. [INFERRED]  
- Authentication/authorization shall be centrally enforced by z/OS Connect security policy. [CONFIRMED]  
- Credentials shall be rotated at least every 90 days. [INFERRED]

**NFR-005 Observability & Auditability**  
- System shall log each invocation with correlationId, timestamp, transactionId, claimId (if present), decisionStatus, latencyMs, and resultCode. [INFERRED]  
- Metrics required: call count, success/failure rate, timeout count, retry count, fallback count, p95 latency. [INFERRED]  
- Alerting shall trigger when fallback rate >5% over 5 minutes. [INFERRED]

**NFR-006 Maintainability**  
- Integration logic (HTTP/JSON mapping) shall remain outside COBOL business modules. [CONFIRMED]  
- Mapping/config changes shall be deployable without COBOL business logic rewrite. [INFERRED]

**NFR-007 Testability**  
- Automated integration test suite shall cover success + all defined error flows with ≥90% requirement coverage across FR-101..FR-302. [INFERRED]  
- Contract tests shall validate decision enum and mapping integrity on every release. [INFERRED]

**NFR-008 Compliance & Data Governance**  
- Claim integration logging shall avoid raw sensitive payload persistence unless explicitly approved by compliance policy. [INFERRED]  
- Data retention for audit events shall be minimum 7 years for regulated insurance operations. [INFERRED]

**NFR-009 Disaster Recovery**  
- RTO target: 4 hours; RPO target: 15 minutes for integration configuration/audit data. [INFERRED]

---

## 9. Risks & Mitigations

1. **R-001 Incomplete copybook field specification**  
   - **Rating:** HIGH  
   - **Justification:** Field-level contract mismatch can break runtime mapping.  
   - **Mitigation:** Freeze copybook contract; add schema conformance tests per release; version `.ara` with copybook hash. [INFERRED]

2. **R-002 External API latency/unavailability**  
   - **Rating:** HIGH  
   - **Justification:** Direct dependency for decision retrieval. [CONFIRMED]  
   - **Mitigation:** Timeout/retry policy, fallback to `PENDING_REVIEW`, operational alerts, and incident runbook. [INFERRED]

3. **R-003 z/OS Connect runtime outage**  
   - **Rating:** HIGH  
   - **Justification:** Central runtime for transformation/security/call handling. [CONFIRMED]  
   - **Mitigation:** HA deployment, health checks, DR plan with RTO/RPO targets. [INFERRED]

4. **R-004 Performance overhead from transformation/network**  
   - **Rating:** MEDIUM  
   - **Justification:** Source explicitly notes JSON and network latency risk. [CONFIRMED]  
   - **Mitigation:** Capacity testing, tuning connection pools/timeouts, latency SLO monitoring. [INFERRED]

5. **R-005 Artifact/version incompatibility (`.ara/.aar/.sar`)**  
   - **Rating:** MEDIUM  
   - **Justification:** Source identifies version compatibility risk. [CONFIRMED]  
   - **Mitigation:** Version pinning, compatibility matrix, gated deployment validation. [INFERRED]

6. **R-006 Security misconfiguration in centralized authn/authz**  
   - **Rating:** MEDIUM  
   - **Justification:** Security posture depends on z/OS Connect policy correctness. [CONFIRMED]  
   - **Mitigation:** Security baseline templates, pre-prod penetration tests, credential rotation controls, policy-as-code checks. [INFERRED]

7. **R-007 Audit/compliance gaps for claim decisions**  
   - **Rating:** MEDIUM  
   - **Justification:** Insurance decisions require traceability and evidentiary logs. [INFERRED]  
   - **Mitigation:** Mandatory audit schema, retention policy enforcement, compliance review gates in release process. [INFERRED]
"""


DUMMY_PRD_STREAM_EVENTS = [
  ("🔎 [Step 1/4] Analyzing source files...", 0.3),
  ("Found 272 files in 24 modules (1119209 chars total)", 0.2),
  ("Invoking analysis agent with 24 modules...", 0.3),
  ("[TOOL] list_modules() — 24 modules available", 0.2),
  ("[TOOL] get_module_source('src') — returning 214648 chars", 0.2),
  ("   API call completed", 0.4),
  ("[TOOL] get_module_source('src/packets') — returning 139938 chars", 0.2),
  ("   API call completed", 0.4),
  ("[TOOL] get_module_source('src/encoding') — returning 110180 chars", 0.2),
  ("   API call completed", 0.4),
  ("[TOOL] get_module_source('codegen/generators') — returning 77538 chars", 0.2),
  ("   API call completed", 0.3),
  ("Analysis complete. 24 modules, 374866 chars total", 0.3),
  ("📝 [Step 2/4] Generating PRD from analysis...", 0.3),
  ("Invoking Claude (claude-opus-4-7) for PRD generation...", 2.0),
  ("   Claude (claude-opus-4-7) API call completed", 0.1),
  ("Claude responded in 354s — PRD generated (52615 chars)", 0.3),
  ("🔍 [Step 3/4] Reviewing PRD (iteration 1)...", 0.3),
  ("Invoking Codex (gpt-5.3-codex) for PRD review...", 1.5),
  ("   Codex (gpt-5.3-codex) API call completed", 0.1),
  ("Codex responded in 24s", 0.1),
  ("Review score: 72/100 (Grade: C)", 0.1),
  ("New best score: 72 (previous best: 0)", 0.1),
  ("Score 72/100 < 80, refining...", 0.2),
  ("🔧 [Step 4/4] Reconciling PRD (iteration 1)...", 0.3),
  ("Invoking Claude (claude-opus-4-7) for PRD reconciliation...", 2.0),
  ("   Claude (claude-opus-4-7) API call completed", 0.1),
  ("Claude responded in 495s — Reconciled PRD (77051 chars)", 0.3),
  ("🔍 [Step 3/4] Reviewing PRD (iteration 2)...", 0.3),
  ("Invoking Codex (gpt-5.3-codex) for PRD review...", 1.5),
  ("   Codex (gpt-5.3-codex) API call completed", 0.1),
  ("Codex responded in 28s", 0.1),
  ("Review score: 58/100 (Grade: D)", 0.1),
  ("Score 58/100 < 80, refining...", 0.2),
  ("🔧 [Step 4/4] Reconciling PRD (iteration 2)...", 0.3),
  ("Invoking Claude (claude-opus-4-7) for PRD reconciliation...", 2.0),
  ("   Claude (claude-opus-4-7) API call completed", 0.1),
  ("Claude responded in 584s — Reconciled PRD (93288 chars)", 0.3),
  ("🔍 [Step 3/4] Reviewing PRD (iteration 3)...", 0.3),
  ("Invoking Codex (gpt-5.3-codex) for PRD review...", 1.5),
  ("   Codex (gpt-5.3-codex) API call completed", 0.1),
  ("Codex responded in 24s", 0.1),
  ("Review score: 67/100 (Grade: C)", 0.1),
  ("Score 67/100 < 80, refining...", 0.2),
  ("🔧 [Step 4/4] Reconciling PRD (iteration 3)...", 0.3),
  ("Invoking Claude (claude-opus-4-7) for PRD reconciliation...", 2.0),
  ("   Claude (claude-opus-4-7) API call completed", 0.1),
  ("Claude responded in 412s — Reconciled PRD (98847 chars)", 0.3),
  ("🔍 [Step 3/4] Reviewing PRD (iteration 4)...", 0.3),
  ("Invoking Codex (gpt-5.3-codex) for PRD review...", 1.5),
  ("   Codex (gpt-5.3-codex) API call completed", 0.1),
  ("Codex responded in 21s", 0.1),
  ("Review score: 85/100 (Grade: B)", 0.1),
  ("New best score: 85 (previous best: 72)", 0.1),
  ("✅ Done (score >= 80). Final score: 85/100", 0.3),
]


__all__ = ["DUMMY_PRD_TEXT", "DUMMY_PRD_STREAM_EVENTS"]
