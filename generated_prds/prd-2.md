# 1. Executive Summary

The Claims Decision Processing System provides claim intake, decisioning, retrieval, and update across two execution channels: online transaction processing and message-driven processing. [CONFIRMED] (Programs: `CLAIMCI0`, `IMSCLAIM`)

The system integrates with an external decision service through requester stub `BAQCSTUB`, targeting API `Sample-Node.js-Claims-Rule-API_1.0`, method `GET`, path `%2Fclaim%2Frule` (decoded `/claim/rule`). [CONFIRMED] (`CLAIMCI0` dependencies; `IMSCLAIM` dependencies)

Primary business outcome: automate first-pass claim adjudication and persist/communicate decisions while preventing false-positive approvals during API failure conditions. [CONFIRMED] (`CLAIMCI0` BR-3/BR-4 logic; `IMSCLAIM` BR-5 mapping)

In-scope capabilities:
- CICS claim transaction processing for submit/read/update using VSAM KSDS file `CLAIMCIF`. [CONFIRMED] (`DO-SUBMIT-CLAIM-REC`, `DO-READ-CLAIM-REC`, `DO-UPDATE-CLAIM-REC`, `DO-REWRITE-CLAIM-REC`)
- IMS queue-driven claim processing loop (`GU` input, API call, `ISRT` output). [CONFIRMED] (`IMSCLAIM DO-MAIN`, `GET-INPUT-MESSAGE`, `SET-OUTPUT-MESSAGE`)
- Operational logging through CICS transient data queue `CSMT` and IMS logging paragraph `LOG-MESSAGE`. [CONFIRMED] (`DO-WRITE-TO-CSMT`, `LOG-MESSAGE`)

Implementation blockers:
- Field-level copybook layouts (PIC clauses, lengths, OCCURS/REDEFINES, offsets) are not present in available analysis payload; detailed schema cannot be finalized until direct copybook extraction from `claim*.cpy`, `imsclaic.cpy`, and `BAQRINFO`. [UNKNOWN]

---

# 2. System Overview

## 2.1 Business Domain
Healthcare claim decision support for submissions requiring rule-based acceptance or review. [INFERRED]

## 2.2 System Purpose
- `CLAIMCI0` is the synchronous transaction processor. It validates request context, routes by action code, calls the decision API for submit operations, persists claim records, and returns a response container. [CONFIRMED] (`DO-INITIALIZATION`, `DO-MAIN-CONTROL`, `DO-SUBMIT-CLAIM-REC`, `DO-RETURN-TO-CICS`)
- `IMSCLAIM` is the asynchronous queue processor. It reads IMS input messages, calls the same API, builds output messages, loops until end-of-message condition, and terminates requester session via `BAQCTERM`. [CONFIRMED] (`DO-MAIN`, `GET-INPUT-MESSAGE`, `CALL-API`, `SET-OUTPUT-MESSAGE`)

## 2.3 Logical Architecture
- Decision Integration Layer: `BAQCSTUB` requester with control structure `BAQRINFO`; teardown via `BAQCTERM` in IMS flow. [CONFIRMED]
- Transaction Persistence Layer: CICS file resource `CLAIMCIF` (VSAM KSDS), using `WRITE`, `READ`, `READ UPDATE`, `REWRITE`. [CONFIRMED]
- Messaging Layer: IMS DL/I via `CBLTDLI`, using I/O PCB (`IO-PCB-MASK`), operations `GU` and `ISRT`. [CONFIRMED]
- Observability Layer: CICS `WRITEQ TD QUEUE(CSMT)` and IMS `LOG-MESSAGE`. [CONFIRMED]

## 2.4 Glossary
- **BAQCSTUB**: API requester stub used by both programs to invoke REST service. [CONFIRMED]
- **BAQCTERM**: API requester session teardown routine used by `IMSCLAIM`. [CONFIRMED]
- **CSMT**: CICS transient data queue for operational logging. [CONFIRMED]
- **PCB**: IMS Program Communication Block (`IO-PCB-MASK`) used for DL/I status and message operations. [CONFIRMED]
- **ZCEE**: z/OS Connect EE-related API error path referenced in source-rule analysis for API failure handling. [CONFIRMED] (Business rule BR-4 analysis text)

---

# 3. Functional Requirements

## Feature Area A — CICS Claim Transaction Handling (`CLAIMCI0`)

### FR-A1: Action-based operation routing
**Requirement:** The system shall route claim requests by action code. [CONFIRMED] (`DO-MAIN-CONTROL`)  
**Input:** Request container `REQ-CLAIM-CONTAINER` (copybook `CLAIMRQC`) including action field. [CONFIRMED]  
**Processing:**  
1) `S` routes to `DO-SUBMIT-CLAIM-REC`  
2) `R` routes to `DO-READ-CLAIM-REC`  
3) `U` routes to `DO-UPDATE-CLAIM-REC`  
4) Any other value routes to unknown-operation error path and logging. [CONFIRMED]  
**Output:** Response container `RSP-CLAIM-CONTAINER` (`CLAIMRSC`) and/or CSMT log entry. [CONFIRMED]  
**Acceptance Criteria:**  
- AC1: Action=`S` executes submit path only.  
- AC2: Action=`R` executes read path only.  
- AC3: Action=`U` executes update path only.  
- AC4: Invalid action values (`space`, lowercase `s`, numeric `1`, multi-char content) invoke unknown-operation path and no `WRITE/REWRITE` to `CLAIMCIF`. [CONFIRMED/INFERRED]  
- AC5: Missing action field in request payload invokes unknown-operation or initialization error path and no file mutation. [INFERRED]

### FR-A2: Initialization and CICS context validation
**Requirement:** The system shall validate required CICS channel/container context before business processing. [CONFIRMED] (`DO-INITIALIZATION`)  
**Input:** CICS channel and `REQ-CLAIM-CONTAINER`. [CONFIRMED]  
**Processing:**  
- Validate channel/container presence and readability before entering action routing. [CONFIRMED]  
- On invalid context, terminate business flow and emit error response/log. [CONFIRMED]  
**Output:**  
- Valid context: control passes to `DO-MAIN-CONTROL`.  
- Invalid context: error response and diagnostic logging; no file operation. [CONFIRMED]  
**Acceptance Criteria:**  
- AC1: Missing/invalid channel or container prevents submit/read/update operations.  
- AC2: Validation failure writes at least one operational error entry (`CSMT`) or equivalent error trace. [INFERRED]  
- AC3: Response structure returns non-success result code field in `CLAIMRSC` when context validation fails. [INFERRED]

### FR-A3: Submit new claim with decision API call
**Requirement:** The system shall normalize claim type, invoke the rules API, map decision result, and persist a new claim record. [CONFIRMED] (`DO-SUBMIT-CLAIM-REC`, `DO-CALL-CLAIM-RULE`)  
**Input:** Submit request from `CLAIMRQC`; API structures `CLAIMREQ` + `CLAIMINF`. [CONFIRMED]  
**Processing:**  
1) Normalize claim type per BR-002. [CONFIRMED]  
2) Invoke API via `BAQCSTUB` (`GET /claim/rule`). [CONFIRMED]  
3) If API call is successful and response decision equals literal `Accepted`, set claim status to `OKAY`; otherwise set `PEND`. [CONFIRMED for literal behavior, case-normalization unspecified]  
4) On API/requester error path, force pending/error path and log diagnostic context to `CSMT`. [CONFIRMED]  
5) Persist claim using `EXEC CICS WRITE FILE(CLAIMCIF)`. [CONFIRMED]  
**Output:** Persisted claim record and populated `CLAIMRSC`. [INFERRED]  
**Acceptance Criteria:**  
- AC1: API success + decision exactly `Accepted` results in persisted `ClaimStatus=OKAY`. [CONFIRMED]  
- AC2: API success + any other decision value results in persisted `ClaimStatus=PEND`. [CONFIRMED]  
- AC3: API invocation failure (timeout/transport/stub/system) results in non-success response path and `ClaimStatus=PEND`; diagnostic log produced. [CONFIRMED/INFERRED]  
- AC4: Exactly one `WRITE CLAIMCIF` occurs for each valid submit transaction. [CONFIRMED]  
- AC5: Decision comparison case/whitespace handling is undefined until API contract specifies accepted-value canonicalization. [UNKNOWN]

### FR-A4: Read existing claim
**Requirement:** The system shall retrieve existing claim data by key from persistent storage. [CONFIRMED] (`DO-READ-CLAIM-REC`, `EXEC CICS READ FILE(CLAIMCIF)`)  
**Input:** Read request with claim key in `CLAIMRQC`. [INFERRED]  
**Processing:** Execute `READ` on `CLAIMCIF`; map retrieved record to `CLAIMRSC`. [CONFIRMED]  
**Output:** Claim details or read-not-found/non-success result. [INFERRED]  
**Acceptance Criteria:**  
- AC1: Existing key returns record content in response container.  
- AC2: Missing key returns non-success response and performs no write/rewrite. [INFERRED]  
- AC3: Read operation is non-mutating under all outcomes. [CONFIRMED]

### FR-A5: Update existing claim
**Requirement:** The system shall update an existing claim using read-for-update and rewrite semantics. [CONFIRMED] (`DO-UPDATE-CLAIM-REC`, `DO-REWRITE-CLAIM-REC`)  
**Input:** Update request with key and mutable fields in `CLAIMRQC`. [INFERRED]  
**Processing:**  
1) `READ FILE(CLAIMCIF) UPDATE`  
2) Apply field updates  
3) `REWRITE FILE(CLAIMCIF)` [CONFIRMED]  
**Output:** Updated claim and response container. [INFERRED]  
**Acceptance Criteria:**  
- AC1: Existing key completes `READ UPDATE` then `REWRITE` with updated values.  
- AC2: Missing key returns non-success path and no `REWRITE`. [INFERRED]  
- AC3: Detailed lock-conflict semantics (retry vs fail-fast vs last-write-wins) are not explicit in available source analysis and require platform exception-spec definition before implementation sign-off. [UNKNOWN]

### FR-A6: CICS operational logging
**Requirement:** The system shall write diagnostic and error messages to CICS TD queue `CSMT`. [CONFIRMED] (`DO-WRITE-TO-CSMT`)  
**Input:** Error/diagnostic context from processing sections. [CONFIRMED]  
**Processing:** `EXEC CICS WRITEQ TD QUEUE(CSMT)` with formatted message text. [CONFIRMED]  
**Output:** Operational log entry in CSMT. [CONFIRMED]  
**Acceptance Criteria:**  
- AC1: API failure path produces at least one CSMT log message.  
- AC2: Unknown-operation path produces at least one CSMT log message. [INFERRED]

---

## Feature Area B — IMS Message-Driven Claim Decisioning (`IMSCLAIM`)

### FR-B1: IMS queue consumption loop
**Requirement:** The system shall process IMS input messages in a loop until IMS end-of-message status is reached. [CONFIRMED] (`DO-MAIN`)  
**Input:** IMS input queue message via `GU` (`CBLTDLI`, `IO-PCB-MASK`). [CONFIRMED]  
**Processing:** `GET-INPUT-MESSAGE` → `CALL-API` → `SET-OUTPUT-MESSAGE` and repeat. [CONFIRMED]  
**Output:** One output message insertion (`ISRT`) per processed valid input message. [CONFIRMED]  
**Acceptance Criteria:**  
- AC1: For N valid input messages, N output messages are inserted.  
- AC2: Loop termination is controlled by PCB end-of-message status field. Exact status code value is not present in available analysis and must be defined in IMS interface contract before unit-test implementation. [UNKNOWN]  
- AC3: Test suite must include early-termination and empty-queue scenarios once status code is specified. [INFERRED]

### FR-B2: IMS API decision mapping
**Requirement:** The system shall map API decision outcomes into IMS response messages. [CONFIRMED] (`CALL-API`)  
**Input:** IMS payload (`IMSCLAIC`) and API response (`CLAIMRSP/CLAIMINF`). [CONFIRMED]  
**Processing:**  
- API decision `Accepted` → output status `ACCEPTED`  
- Non-accepted/API failure path → output `REJECTED` with further-review text. [CONFIRMED]  
**Output:** Response payload written through `ISRT`. [CONFIRMED]  
**Acceptance Criteria:**  
- AC1: Decision exactly `Accepted` yields `ACCEPTED`. [CONFIRMED]  
- AC2: Non-accepted decision yields `REJECTED` and review messaging. [CONFIRMED]  
- AC3: Case/whitespace normalization for decision values is undefined until external API contract is finalized. [UNKNOWN]

### FR-B3: API requester teardown
**Requirement:** The system shall terminate API requester session state at end of IMS processing lifecycle. [CONFIRMED] (`DO-MAIN` calls `BAQCTERM`)  
**Input:** End-of-processing event in `DO-MAIN`. [CONFIRMED]  
**Processing:** Invoke `BAQCTERM` once per program lifecycle. [CONFIRMED]  
**Output:** Requester session teardown completed. [INFERRED]  
**Acceptance Criteria:**  
- AC1: Runtime execution trace or call instrumentation confirms one `BAQCTERM` invocation after loop completion per run instance. [CONFIRMED/INFERRED]

### FR-B4: IMS operational logging
**Requirement:** The system shall log processing and API statuses in IMS logging logic. [CONFIRMED] (`LOG-MESSAGE`)  
**Input:** Processing context (API outcome, message progression, errors). [CONFIRMED]  
**Processing:** Execute `LOG-MESSAGE` paragraph to emit trace text. [CONFIRMED]  
**Output:** Operational trace for diagnosis. [CONFIRMED]  
**Acceptance Criteria:**  
- AC1: API error paths generate at least one log entry with message context. [INFERRED]

---

# 4. Data Model

## 4.1 Canonical Entities
1) **ClaimRecord** (persisted via `CLAIMCIF`) [CONFIRMED]  
2) **CicsClaimRequest** (`CLAIMRQC`) [CONFIRMED]  
3) **CicsClaimResponse** (`CLAIMRSC`) [CONFIRMED]  
4) **ClaimApiRequest** (`CLAIMREQ` + `CLAIMINF`) [CONFIRMED]  
5) **ClaimApiResponse** (`CLAIMRSP` + `CLAIMINF`) [CONFIRMED]  
6) **ImsClaimMessage** (`IMSCLAIC`) [CONFIRMED]  
7) **ApiControlInfo** (`BAQRINFO`) [CONFIRMED]

## 4.2 Physical Data Dictionary Baseline

Field-level PIC details are partially unavailable in the provided analysis dump; only structures and business use are confirmed. Attributes below are implementation-facing structural contracts and must be finalized with direct copybook extraction (`*.cpy`) before build. [UNKNOWN]

| Entity | Attribute | Required | Source Trace | Type |
|---|---|---|---|---|
| ClaimRecord | claimKey | Yes | `READ/WRITE/REWRITE CLAIMCIF` flows | string [UNKNOWN length] |
| ClaimRecord | claimType | Yes | BR-2 normalization in `DO-SUBMIT-CLAIM-REC` | enum/string |
| ClaimRecord | claimAmount | Yes | README/API behavior context + claim info structures | decimal [UNKNOWN precision] |
| ClaimRecord | claimStatus | Yes | BR-3 (`OKAY/PEND`) | enum |
| CicsClaimRequest | actionCode | Yes | BR-1 routing | string(1) [INFERRED] |
| CicsClaimRequest | claim payload fields | Conditional | `CLAIMRQC` | object [UNKNOWN layout] |
| CicsClaimResponse | response/result fields | Yes | `CLAIMRSC` | object [UNKNOWN layout] |
| ClaimApiRequest | decision input fields | Yes | `CLAIMREQ` + `CLAIMINF` | object [UNKNOWN layout] |
| ClaimApiResponse | decision value | Yes | BR-3 / BR-5 uses `Accepted` comparison | string |
| ImsClaimMessage | input fields | Yes | `IMSCLAIC` + `GU` | object [UNKNOWN layout] |
| ImsClaimMessage | output status/message | Yes | BR-5 + `ISRT` | object [UNKNOWN layout] |
| ApiControlInfo | requester metadata | Yes | `BAQRINFO` | object [UNKNOWN layout] |

## 4.3 Keys and Relationships
- `ClaimRecord.claimKey` is the storage key used in CICS read/update/write transactions. [CONFIRMED/INFERRED]
- One submit request (`CicsClaimRequest` action `S`) creates one `ClaimRecord`. [CONFIRMED/INFERRED]
- One `ClaimRecord` can be read or updated by multiple transactions over time. [INFERRED]
- One API request maps to one API response per invocation in both channels. [CONFIRMED]
- One IMS input message yields one IMS output message in normal flow. [CONFIRMED]
- Foreign-key relationships are not explicitly modeled in source; dataset is key-addressable record storage. [CONFIRMED/INFERRED]

## 4.4 COBOL-to-Modern Type Mapping
- PIC X(n) → string  
- PIC 9(n) → integer  
- PIC 9(n)V9(m) → decimal  
- OCCURS → array/list  
- REDEFINES → union/variant view  
Actual field mappings require copybook extraction. [UNKNOWN]

---

# 5. Process Flows

## 5.1 CICS Transaction Flow (`CLAIMCI0`)
1) Receive request container (`CLAIMRQC`) in CICS channel. [CONFIRMED]  
2) `DO-INITIALIZATION` validates channel/container context. [CONFIRMED]  
3) `DO-MAIN-CONTROL` dispatches by action code (`S`,`R`,`U`,other). [CONFIRMED]  
4) Submit path (`DO-SUBMIT-CLAIM-REC`): normalize type → call API (`DO-CALL-CLAIM-RULE`) → map status (`OKAY/PEND`) → `WRITE CLAIMCIF`. [CONFIRMED]  
5) Read path: `READ CLAIMCIF` and map response. [CONFIRMED]  
6) Update path: `READ ... UPDATE` → apply modifications → `REWRITE CLAIMCIF`. [CONFIRMED]  
7) Error/diagnostic conditions use `DO-WRITE-TO-CSMT`. [CONFIRMED]  
8) `DO-RETURN-TO-CICS` returns response container. [CONFIRMED]

### CICS Error Flow
- API/requester failure in `DO-CALL-CLAIM-RULE` triggers pending/error path and logging, preventing success approval. [CONFIRMED]  
- Post-decision persistence failure handling exists as non-success path, but compensation/idempotent replay behavior is not explicit in analysis data. [UNKNOWN]

## 5.2 IMS Message Flow (`IMSCLAIM`)
1) `DO-MAIN` enters processing loop. [CONFIRMED]  
2) `GET-INPUT-MESSAGE` performs `GU` using `CBLTDLI`. [CONFIRMED]  
3) `CALL-API` invokes `BAQCSTUB` and maps decision to output status. [CONFIRMED]  
4) `SET-OUTPUT-MESSAGE` performs `ISRT`. [CONFIRMED]  
5) Repeat until PCB indicates end-of-message condition. [CONFIRMED/UNKNOWN exact code]  
6) Call `BAQCTERM` once after loop completes. [CONFIRMED]

### IMS Error Flow
- API failure leads to non-accepted response mapping and logging via `LOG-MESSAGE`. [CONFIRMED/INFERRED]  
- Dead-letter routing, poison-message quarantine, and duplicate-message idempotency strategy are not explicit in analyzed source. [UNKNOWN]

---

# 6. Business Rules

| ID | Rule Statement | Type | Verification Method | Source |
|---|---|---|---|---|
| BR-001 | Action `S/R/U` routes to submit/read/update; other values route to unknown-operation path. | Routing | Dispatcher unit/integration tests | `CLAIMCI0 DO-MAIN-CONTROL` [CONFIRMED] |
| BR-002 | Submit flow normalizes claim type: DRUG(4), DENTAL(6), MEDICAL(7), else default MEDICAL. | Normalization | Unit tests including blanks/lowercase/padded input | `CLAIMCI0 DO-SUBMIT-CLAIM-REC` [CONFIRMED] |
| BR-003 | CICS decision mapping: API success + decision literal `Accepted` sets status `OKAY`; all other outcomes set `PEND`. | Decision Mapping | API response variant tests | `CLAIMCI0 DO-CALL-CLAIM-RULE` [CONFIRMED] |
| BR-004 | On API/ZCEE/stub error path, system logs and forces pending/error path (no success approval). | Error Handling | Fault-injection tests | `CLAIMCI0 DO-CALL-CLAIM-RULE`, `DO-WRITE-TO-CSMT` [CONFIRMED] |
| BR-005 | IMS decision mapping: decision `Accepted` => `ACCEPTED`; non-accepted => `REJECTED` with further-review message. | Decision Mapping | IMS integration tests | `IMSCLAIM CALL-API` [CONFIRMED] |
| BR-006 | IMS loop runs GU→API→ISRT until end-of-message condition. | Processing Loop | IMS queue functional tests | `IMSCLAIM DO-MAIN` [CONFIRMED] |
| BR-007 | `BAQCTERM` is called after IMS processing to close requester session state. | Resource Lifecycle | Runtime trace verification | `IMSCLAIM DO-MAIN` [CONFIRMED] |
| BR-008 | API decision literal matching/case-normalization behavior is unspecified in available source analysis; exact contract must be defined by API interface spec. | Contract Constraint | API contract review + integration tests | API comparison behavior in BR-003/BR-005 [UNKNOWN] |

---

# 7. External Interfaces

## 7.1 Decision Rules API
- Consumers: `CLAIMCI0`, `IMSCLAIM`. [CONFIRMED]  
- Invocation: `BAQCSTUB` with control via `BAQRINFO`. [CONFIRMED]  
- API target: `Sample-Node.js-Claims-Rule-API_1.0`  
- Method/path: `GET /claim/rule` (encoded `%2Fclaim%2Frule`). [CONFIRMED]  
- Request structures: `CLAIMREQ`, `CLAIMINF`. [CONFIRMED]  
- Response structures: `CLAIMRSP`, `CLAIMINF`. [CONFIRMED]

### Proposed API Error Classification (implementation contract proposal)
The source confirms error-path branching but does not expose normalized error taxonomy names. Proposed classes below are implementation design controls. [INFERRED]  
- `API-ERR-TIMEOUT`  
- `API-ERR-TRANSPORT`  
- `API-ERR-STUB`  
- `API-ERR-REMOTE`  
- `API-ERR-MALFORMED`  
Fallback for all classes: non-accepted outcome + operational logging. [CONFIRMED/INFERRED]

## 7.2 CICS File Interface
- File: `CLAIMCIF` (VSAM KSDS). [CONFIRMED]  
- Operations: `WRITE`, `READ`, `READ UPDATE`, `REWRITE`. [CONFIRMED]

## 7.3 CICS Log Interface
- Queue: `CSMT`. [CONFIRMED]  
- Operation: `WRITEQ TD`. [CONFIRMED]

## 7.4 IMS Messaging Interface
- DL/I entry point: `CBLTDLI`. [CONFIRMED]  
- Input op: `GU`. [CONFIRMED]  
- Output op: `ISRT`. [CONFIRMED]  
- Message layout: `IMSCLAIC`. [CONFIRMED]  
- Control block: `IO-PCB-MASK`. [CONFIRMED]

---

# 8. Non-Functional Requirements

All quantitative targets below are implementation baselines pending production profiling and platform capacity validation unless explicitly confirmed by source behavior. [INFERRED]

## 8.1 Performance
- CICS submit end-to-end latency target: p95 ≤ 2.5s including API roundtrip. [INFERRED]  
- CICS read/update latency target: p95 ≤ 500ms excluding external API (not used in read/update). [INFERRED]  
- IMS processing latency target: p95 ≤ 300ms per message excluding API delay; p95 ≤ 2.5s including API delay. [INFERRED]  
- API call timeout baseline: 5s. [INFERRED]

## 8.2 Scalability
- CICS baseline capacity: 200 concurrent active tasks per region without SLA breach. [INFERRED]  
- IMS sustained throughput baseline: 10,000 messages/hour; backlog handling up to 50,000 queued messages. [INFERRED]  
- Platform tuning dependencies (CICS region sizing, IMS MPR count) must be defined during performance test planning. [UNKNOWN]

## 8.3 Availability & Reliability
- Availability target: 99.9% monthly during processing windows. [INFERRED]  
- Reliability invariant: API failure must never produce accepted/OKAY approval outcome. [CONFIRMED]  
- Recovery objectives: RTO 60 minutes; RPO 15 minutes. [INFERRED]  
- Backup restore validation cadence: quarterly restore test minimum. [INFERRED]

## 8.4 Security & Compliance
- Transport security and API authentication mechanism (mTLS vs token) must be formally specified before production release. [UNKNOWN]  
- Log outputs must mask sensitive claim/member fields. [INFERRED]  
- Data-at-rest encryption must be enabled for claim datasets and backups (algorithm/key management to be specified). [UNKNOWN]  
- Access control model (submit/read/update entitlements) must be defined in interface governance. [UNKNOWN]  
- Compliance obligations (e.g., HIPAA/SOC2) must be confirmed by governance prior to go-live. [UNKNOWN]

## 8.5 Observability
- Required metrics: API success/failure rate, timeout rate, CICS latency p50/p95, IMS queue depth, file operation error count. [INFERRED]  
- Correlation strategy: include transaction/message correlation ID across CICS logs, IMS logs, and API calls where available. [INFERRED]  
- Alert thresholds: API failure >2% for 5 min; IMS depth >10,000; repeated file write failures >5/min. [INFERRED]  
- Log retention baseline: 90 days online searchable + archive per enterprise policy. [INFERRED]

## 8.6 Testability
- Mandatory automated coverage: all routing branches, decision mappings, container validation failures, API failure paths, and file operation error paths. [CONFIRMED/INFERRED]  
- Deterministic testing requires API requester mocking or fault-injection harness for `BAQCSTUB`. [INFERRED]  
- Acceptance test matrix must include: missing action, invalid action, missing container, non-existent key, update-not-found, API success/non-success, IMS loop termination, BAQCTERM invocation. [INFERRED]

## 8.7 Maintainability
- Code changes must preserve paragraph-level traceability between requirements and implementation sections (`DO-*`, `CALL-API`, `GET-INPUT-MESSAGE`, etc.). [INFERRED]  
- Update impact analysis must include copybook contract diffing before deployment. [INFERRED]  
- Operational runbooks must be maintained for API outage, queue backlog, and file failure scenarios. [INFERRED]

---

# 9. Risks & Mitigations

| Risk | Severity | Justification | Mitigation | Owner |
|---|---|---|---|---|
| Missing field-level data contract (copybook PIC/OCCURS/REDEFINES absent) | HIGH | Build-blocking for serialization, validation, and schema mapping | Extract full copybooks (`CLAIMRQC`, `CLAIMRSC`, `CLAIMREQ`, `CLAIMRSP`, `CLAIMINF`, `IMSCLAIC`, `BAQRINFO`) and freeze data dictionary before design freeze | Mainframe Tech Lead |
| IMS end-of-message status code undefined | HIGH | Loop correctness depends on exact PCB status semantics | Obtain IMS status contract, codify in FR-B1 tests, and implement explicit termination checks before integration testing | IMS Lead |
| API decision-string contract undefined (case/whitespace/encoding) | HIGH | Literal `Accepted` comparisons may misclassify outcomes | Publish API decision contract and implement canonicalization rules with regression tests before integration testing | Integration Architect + API Owner |
| Undefined security posture before production | HIGH | Audit/compliance failure risk (auth, encryption, access control unresolved) | Finalize security profile (authn/authz, TLS, key mgmt, masking, retention) before production readiness review | Security Architect |
| External API outage or requester failure | HIGH | Both processing channels depend on external decision service | Enforce timeout, fallback non-accepted path, observability alarms, and controlled retry policy | Integration Architect |
| Partial-write data integrity risk after API decision | HIGH | API may succeed while persistence fails, causing inconsistent processing outcomes | Define compensating action/idempotent retry/runbook and reconciliation reporting before UAT | CICS Platform Owner |
| Lock/contention semantics for update not fully specified | MEDIUM | `READ UPDATE/REWRITE` conflict behavior not explicit in available analysis | Define platform-standard contention handling and test scenarios before system testing | CICS Platform Owner |
| IMS poison message / duplicate processing risk | MEDIUM | Source does not define dead-letter or idempotency strategy | Implement validation gate, retry cap, DLQ/quarantine policy, and duplicate detection design before cutover | IMS Lead |
| Dependency lifecycle risk (BAQCSTUB/API contract changes) | MEDIUM | Interface break can halt adjudication flows | Version pinning, contract tests, and change-notification governance with API provider | Enterprise Architect |
| NFR baselines unvalidated | MEDIUM | Current targets are planning values, not measured commitments | Execute performance/capacity tests and calibrate SLOs prior to production sign-off | SRE Lead |
| Operational log saturation (`CSMT`/IMS logs) | LOW | Error storms may reduce diagnosability | Add throttling/sampling and queue utilization monitoring before production cutover | Operations Lead |