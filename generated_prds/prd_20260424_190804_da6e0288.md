# Product Requirements Document (PRD)
## Claims Decisioning & Persistence Platform — Mainframe Integration with REST API Requester

**Document Status:** Final v2.0
**Source Basis:** Static analysis of the `zosconnect-sample-cobol-apirequester` repository (2 COBOL programs: `CLAIMCI0`, `IMSCLAIM`; 7 copybooks: `CLAIMREQ`, `CLAIMRSP`, `CLAIMINF`, `CLAIMRQC`, `CLAIMRSC`, `IMSCLAIC`, `BAQRINFO`).

**Evidence Tag Legend:**
- `[CONFIRMED]` — Directly observable in program source or copybook (procedure paragraph, CALL, EXEC CICS/DLI verb, or PIC clause explicitly referenced).
- `[INFERRED]` — Reasonably deduced from available artifacts but not explicitly stated.
- `[UNKNOWN]` — Not determinable from analysis data; requires additional investigation.

---

## 1. Executive Summary

### 1.1 Purpose
This PRD specifies the functional and non-functional requirements for a mainframe-based **Health Insurance Claims Decisioning & Persistence Platform**. The platform consists of two integration programs that accept inbound claim requests from CICS and IMS channels, invoke an external **Claims Rule REST API** through IBM z/OS Connect V3 API Requester, and persist claim records to a VSAM KSDS dataset. `[INFERRED]` — based on program naming (`CLAIMCI0`, `IMSCLAIM`), copybook field names (`REQ-CLAIM-*`, `claimType`, `claimAmount`), and the fixed API path `/claim/rule` in copybook `CLAIMINF`.

### 1.2 Business Domain
**Health Insurance Claims Processing.** `[INFERRED]`

The platform:
- Accepts inbound claim submissions and queries via two transport channels: CICS channel/container and IMS message queue. `[CONFIRMED]`
- Invokes an external Claims Rule REST API (name `Sample-Node.js-Claims-Rule-API_1.0`, path `/claim/rule`, method `GET`). `[CONFIRMED — copybook CLAIMINF]`
- Persists claim records keyed by Claim ID in a VSAM KSDS file named `CLAIMCIF`. `[CONFIRMED — CICS file-control name]`
- Returns a decision (approved, pended, rejected, or error) to the calling channel.

### 1.3 Scope of Analyzed Components

| Component | Type | Role | Evidence |
|---|---|---|---|
| `CLAIMCI0` | CICS COBOL program | Submit / Read / Update claim records; call Claims Rule API | `[CONFIRMED]` |
| `IMSCLAIM` | IMS COBOL program | Receive IMS messages; call Claims Rule API; respond with decision | `[CONFIRMED]` |
| `BAQCSTUB` | External module | z/OS Connect API Requester stub (invoked by both programs) | `[CONFIRMED]` |
| `BAQCTERM` | External module | z/OS Connect requester connection cleanup (called by IMSCLAIM only) | `[CONFIRMED]` |
| `CBLTDLI` | External module | IMS DL/I interface (GU/GN/ISRT) | `[CONFIRMED]` |
| `CLAIMCIF` | VSAM KSDS file | Claim record persistence store | `[CONFIRMED — referenced in CICS file operations]` |
| `CSMT` | CICS TD Queue | Operational log destination | `[CONFIRMED]` |
| Copybooks | Data contracts | `CLAIMREQ`, `CLAIMRSP`, `CLAIMINF`, `CLAIMRQC`, `CLAIMRSC`, `IMSCLAIC`, `BAQRINFO` | `[CONFIRMED]` |

### 1.4 Key Business Capabilities
1. Submit a new claim, invoke decisioning, and persist to file. `[CONFIRMED — DO-SUBMIT-CLAIM-REC]`
2. Retrieve an existing claim by claim ID. `[CONFIRMED — DO-READ-CLAIM-REC]`
3. Update an existing claim under a pessimistic read lock. `[CONFIRMED — DO-UPDATE-CLAIM-REC → DO-REWRITE-CLAIM-REC]`
4. Process inbound IMS claim messages in a loop, returning a decision per message. `[CONFIRMED — IMSCLAIM DO-MAIN]`
5. Emit timestamped operational log entries. `[CONFIRMED]`

### 1.5 Document Status and Usage
This document is the authoritative specification for:
- Engineering implementation and refactoring.
- QA test plan development.
- Architecture and modernization assessment.

Items marked `[UNKNOWN]` require clarification before implementation commitments are made.

---

## 2. System Overview

### 2.1 Logical Architecture

```
        ┌──────────────────────────────────────────────────────┐
        │             CALLING CHANNELS (Clients)               │
        │   CICS Channel/Container ───────┬── IMS Message Q    │
        └──────────────────────┬──────────┴──────────┬─────────┘
                               │                     │
                         ┌─────▼─────┐         ┌─────▼─────┐
                         │ CLAIMCI0  │         │ IMSCLAIM  │
                         │  (CICS)   │         │   (IMS)   │
                         └──┬────┬───┘         └─────┬─────┘
                            │    │                   │
             ┌──────────────▼┐   │  ┌────────────────▼─────────────┐
             │ VSAM KSDS     │   │  │ z/OS Connect API Requester   │
             │ CLAIMCIF      │   │  │ BAQCSTUB → REST (GET)        │
             └───────────────┘   │  │    /claim/rule               │
                                 │  └────────────────┬─────────────┘
                                 │                   │
                         ┌───────▼───────┐    ┌──────▼──────┐
                         │ CSMT TD Queue │    │ External    │
                         │ (logging)     │    │ Claims Rule │
                         └───────────────┘    │ REST API    │
                                              └─────────────┘
```
`[INFERRED — composed from file/call usage in both programs]`

### 2.2 Processing Patterns
- **CLAIMCI0:** Synchronous, online transaction processing over CICS channels/containers. `[CONFIRMED — EXEC CICS ASSIGN CHANNEL / GET CONTAINER / PUT CONTAINER / RETURN]`
- **IMSCLAIM:** Message-driven loop consuming IMS input messages via `GU`, responding via `ISRT`, terminating on PCB status `QC`. `[CONFIRMED — DO-MAIN loop; CBLTDLI calls]`

### 2.3 Deployment Environment Assumptions
- CICS TS region with channel/container support and z/OS Connect V3 API Requester installed. `[CONFIRMED by dependency on BAQCSTUB]`
- IMS TM region with z/OS Connect V3 API Requester and DL/I support. `[CONFIRMED]`
- `CLAIMCIF` defined as VSAM KSDS and available to the CICS region. `[INFERRED — CICS file-control object referenced but DEFINE not in scope]`

### 2.4 Out of Scope (This Analysis)
- z/OS Connect configuration artifacts (API packages, service archives).
- External Claims Rule REST API implementation internals.
- VSAM cluster DEFINE (key offset, length, buffer pools, RLS settings). `[UNKNOWN]`
- Security policy and TLS configuration for API Requester. `[UNKNOWN]`

---

## 3. Functional Requirements

Each requirement is stated in "The system shall..." form with Input / Processing / Output and Given-When-Then acceptance criteria. Original COBOL paragraph and field names are retained in parentheses for traceability.

### Feature Area A — CICS Claim Operations (program `CLAIMCI0`)

#### FR-A1 — Dispatch Claim Operation by Action Code
**Statement:** The system shall route incoming CICS container requests to a Submit, Read, or Update handler based on the single-character action code, and shall reject any other value with an unknown-operation response. `[CONFIRMED — DO-MAIN-CONTROL]`

- **Input:** A request container on the inbound CICS channel containing the `CLAIMRQC` copybook layout, including `REQ-CLAIM-ACTION` (PIC X(1); values `'S'`, `'R'`, `'U'`).
- **Processing:**
  1. Execute `EXEC CICS ASSIGN CHANNEL` to obtain the current channel name. `[CONFIRMED]`
  2. Execute `EXEC CICS STARTBROWSE CONTAINER` followed by `GETNEXT CONTAINER` and `GET CONTAINER` to read request data into `REQ-CLAIM-CONTAINER`. `[CONFIRMED]`
  3. Evaluate `REQ-CLAIM-ACTION` and invoke the matching handler (`DO-SUBMIT-CLAIM-REC`, `DO-READ-CLAIM-REC`, or `DO-UPDATE-CLAIM-REC`). `[CONFIRMED]`
  4. For any other value of `REQ-CLAIM-ACTION`, populate `RSP-CLAIM-OUTPUT-MESSAGE` with an unknown-operation text and skip all file operations. `[INFERRED — based on EVALUATE WHEN OTHER pattern]`
- **Output:** Populated `RSP-CLAIM-CONTAINER` returned through `DO-RETURN-TO-CICS`.
- **Acceptance Criteria:**
  - **AC-A1.1:** *Given* a request with `REQ-CLAIM-ACTION = 'S'`, *when* the program is invoked, *then* the Submit handler (FR-A2) executes and no Read/Update code path runs.
  - **AC-A1.2:** *Given* `REQ-CLAIM-ACTION = 'R'`, *then* the Read handler (FR-A3) executes.
  - **AC-A1.3:** *Given* `REQ-CLAIM-ACTION = 'U'`, *then* the Update handler (FR-A4) executes.
  - **AC-A1.4:** *Given* any other value, *then* `RSP-CLAIM-OUTPUT-MESSAGE` contains an "unknown operation" text (exact wording `[UNKNOWN]`; must be defined during implementation) and no VSAM write/read/rewrite occurs.
  - **AC-A1.5:** *Given* `ASSIGN CHANNEL` or `GETNEXT CONTAINER` returns a non-NORMAL condition, *then* the failure is logged to CSMT (FR-A5) and a diagnostic response is returned. `[INFERRED — exact RESP/RESP2 handling UNKNOWN; must be defined during implementation]`

#### FR-A2 — Submit New Claim Record
**Statement:** The system shall, upon a Submit action, invoke the Claims Rule API, set the claim status based on the API decision, and persist the claim to the `CLAIMCIF` VSAM file. `[CONFIRMED — DO-SUBMIT-CLAIM-REC]`

- **Input:** `REQ-CLAIM-CONTAINER` populated with `REQ-CLAIM-ID`, `REQ-CLAIM-TYPE`, `REQ-CLAIM-AMOUNT`, `REQ-CLAIM-DATE`, `REQ-CLAIM-DESC`, `REQ-CLAIM-PROVIDER`.
- **Processing:**
  1. Copy request fields into the response record structure `RSP-CLAIM-CONTAINER`. `[CONFIRMED]`
  2. Invoke `DO-CALL-CLAIM-RULE`, which calls `BAQCSTUB` (see FR-C1, FR-C2). `[CONFIRMED]`
  3. Set `RSP-CLAIM-STATUS` per BR-003 (`'OKAY'` if `Xstatus2 = 'Accepted'`, else `'PEND'`). `[CONFIRMED]`
  4. Issue `EXEC CICS WRITE FILE('CLAIMCIF') FROM(RSP-CLAIM-CONTAINER) RIDFLD(RSP-CLAIM-ID)`. `[CONFIRMED]`
  5. Capture CICS RESP/RESP2 into `RSP-CLAIM-CICS-RESP` / `RSP-CLAIM-CICS-RESP2`. `[INFERRED — fields exist in copybook CLAIMRSC but explicit MOVE not enumerated]`
  6. Set `RSP-CLAIM-OUTPUT-MESSAGE` to indicate success or failure. `[CONFIRMED]`
- **Output:** Claim record persisted to `CLAIMCIF`; populated response container returned to caller.
- **Acceptance Criteria:**
  - **AC-A2.1:** *Given* a well-formed request and a successful API call returning `Xstatus2 = 'Accepted'`, *when* Submit executes, *then* `RSP-CLAIM-STATUS = 'OKAY'`, the VSAM WRITE returns `DFHRESP(NORMAL)`, `RSP-CLAIM-CICS-RESP = 0`, and `RSP-CLAIM-OUTPUT-MESSAGE` contains a success message.
  - **AC-A2.2:** *Given* a successful API call with any other `Xstatus2` value, *then* `RSP-CLAIM-STATUS = 'PEND'` and the VSAM WRITE still occurs.
  - **AC-A2.3:** *Given* a VSAM WRITE returns `DFHRESP(DUPREC)`, *then* `RSP-CLAIM-CICS-RESP` reflects the DUPREC value, `RSP-CLAIM-OUTPUT-MESSAGE` indicates a duplicate-key condition (exact wording `[UNKNOWN]`), and no retry occurs.
  - **AC-A2.4:** *Given* `BAQCSTUB` returns a non-zero `OUT-API-STATUS-CODE`, *then* `RSP-CLAIM-STATUS = 'PEND'`, the VSAM WRITE still occurs, and a CSMT log line is produced (FR-A5).
  - **AC-A2.5:** *Given* `BAQCSTUB` returns `Xstatus2` in non-matching case (e.g., `'accepted'`, `'ACCEPTED'`), *then* the current exact-match comparison yields `'PEND'` (see risk R-02 and BR-003).

#### FR-A3 — Read Claim Record by ID
**Statement:** The system shall, upon a Read action, retrieve a claim from `CLAIMCIF` by claim ID and return the full claim record or an appropriate not-found / error response. `[CONFIRMED — DO-READ-CLAIM-REC]`

- **Input:** `REQ-CLAIM-CONTAINER` with `REQ-CLAIM-ID`.
- **Processing:** `EXEC CICS READ FILE('CLAIMCIF') INTO(RSP-CLAIM-CONTAINER) RIDFLD(RSP-CLAIM-ID) RESP(RSP-CLAIM-CICS-RESP) RESP2(RSP-CLAIM-CICS-RESP2)`. `[CONFIRMED]`
- **Output:** Populated `RSP-CLAIM-CONTAINER` or a diagnostic message.
- **Acceptance Criteria:**
  - **AC-A3.1:** *Given* a record exists for the requested ID, *then* all `RSP-CLAIM-*` fields are populated from the VSAM record, `RSP-CLAIM-CICS-RESP = 0`, and `RSP-CLAIM-OUTPUT-MESSAGE` contains a success indication.
  - **AC-A3.2:** *Given* no record exists (`DFHRESP(NOTFND)`), *then* `RSP-CLAIM-CICS-RESP` reflects NOTFND, `RSP-CLAIM-OUTPUT-MESSAGE` indicates not-found, and no write or rewrite occurs.
  - **AC-A3.3:** *Given* any other non-NORMAL RESP (e.g., IOERR, FILENOTFOUND), *then* RESP/RESP2 values are surfaced in the response and a CSMT log entry is written.

#### FR-A4 — Update Claim Record
**Statement:** The system shall, upon an Update action, acquire a VSAM update lock by reading the record for update, apply field changes, and rewrite the record. `[CONFIRMED — DO-UPDATE-CLAIM-REC → DO-REWRITE-CLAIM-REC]`

- **Input:** `REQ-CLAIM-CONTAINER` with `REQ-CLAIM-ID` and updated data. The updated status is conveyed via `REQ-FILLER` (PIC X(4)). `[CONFIRMED — see R-07]`
- **Processing:**
  1. `EXEC CICS READ FILE('CLAIMCIF') INTO(RSP-CLAIM-CONTAINER) RIDFLD(RSP-CLAIM-ID) UPDATE` to acquire the record lock. `[CONFIRMED]`
  2. If the read succeeds, move the updated status from `REQ-FILLER` into `RSP-CLAIM-STATUS` and other mutable fields as defined in BR-012. `[INFERRED]`
  3. `EXEC CICS REWRITE FILE('CLAIMCIF') FROM(RSP-CLAIM-CONTAINER)`. `[CONFIRMED]`
- **Output:** Updated record persisted; response with status and CICS response codes.
- **Acceptance Criteria:**
  - **AC-A4.1:** *Given* a successful READ UPDATE, *then* REWRITE executes exactly once and the record lock is released on transaction completion.
  - **AC-A4.2:** *Given* READ UPDATE returns NOTFND, *then* REWRITE is not attempted and `RSP-CLAIM-OUTPUT-MESSAGE` indicates not-found.
  - **AC-A4.3:** *Given* REWRITE fails (non-NORMAL RESP), *then* RESP/RESP2 are surfaced, a CSMT entry is written, and the transaction unit of work is rolled back by CICS default semantics. `[INFERRED — explicit SYNCPOINT/ROLLBACK handling UNKNOWN]`
  - **AC-A4.4:** *Given* a concurrent second transaction attempts READ UPDATE on the same key while a lock is held, *then* the second transaction waits or receives LOCKED per CICS VSAM semantics. `[INFERRED — exact wait/timeout behavior UNKNOWN]`

#### FR-A5 — Operational Logging to CSMT
**Statement:** The system shall write timestamped diagnostic log lines to the CICS `CSMT` transient-data queue for API failures, file errors, and unknown conditions, without aborting the main transaction. `[CONFIRMED — DO-WRITE-TO-CSMT]`

- **Input:** Log text assembled at the point of failure or notable event.
- **Processing:**
  1. `EXEC CICS ASKTIME ABSTIME` and `FORMATTIME` to obtain a human-readable timestamp. `[CONFIRMED]`
  2. Assemble a 121-byte line combining timestamp, program/paragraph identifier, and message. `[CONFIRMED — width observed]`
  3. `EXEC CICS WRITEQ TD QUEUE('CSMT') FROM(log-line)`. `[CONFIRMED]`
- **Output:** A log record appended to the CSMT queue.
- **Acceptance Criteria:**
  - **AC-A5.1:** *Given* any API or CICS file error path executes, *then* exactly one CSMT line is produced containing a formatted timestamp (`YYYY-MM-DD HH:MM:SS` or equivalent) and the error text.
  - **AC-A5.2:** *Given* the CSMT WRITEQ itself fails, *then* the main transaction continues and the logging failure does not propagate an abend. `[INFERRED — verify during implementation]`

### Feature Area B — IMS Claim Processing (program `IMSCLAIM`)

#### FR-B1 — Process Inbound IMS Message Loop
**Statement:** The system shall consume IMS input messages in a loop, produce one output message per input, and terminate cleanly when the IO-PCB status code equals `'QC'`. `[CONFIRMED — DO-MAIN]`

- **Input:** IMS input messages containing the `IMSCLAIC.INPUT-MSG` layout (`IN-LL`, `IN-ZZ`, `IN-TRANCODE`, `IN-CLAIM-TYPE`, `IN-CLAIM-DATE`, `IN-CLAIM-AMOUNT`, `IN-CLAIM-DESC`).
- **Processing:**
  1. `CALL 'CBLTDLI' USING GU, IO-PCB-MASK, INPUT-MSG`. `[CONFIRMED]`
  2. If `PCB-STATUS = 'QC'`, exit the loop.
  3. If `PCB-STATUS` is any other non-space value, log and exit.
  4. Otherwise, perform `CALL-API` (FR-B2) and `SET-OUTPUT-MESSAGE`, then `CALL 'CBLTDLI' USING ISRT, IO-PCB-MASK, OUTPUT-MSG`. `[CONFIRMED]`
  5. Loop.
- **Output:** One `OUTPUT-MSG` per consumed input message.
- **Acceptance Criteria:**
  - **AC-B1.1:** *Given* N input messages and a final `QC` status, *then* N output messages are inserted and the program returns control to IMS cleanly.
  - **AC-B1.2:** *Given* a non-`QC`, non-space PCB status (e.g., `AD`, `AB`), *then* a log line via `LOG-MESSAGE` is produced and the program exits. `[CONFIRMED — unexpected PCB logged]`
  - **AC-B1.3:** *Given* no input messages available, *then* no output is produced and the program exits on the first `QC`.

#### FR-B2 — Claim Decision via REST API (IMS)
**Statement:** The system shall build a Claims Rule API request from each input message, invoke the API via `BAQCSTUB`, map the response to a canonical decision (`ACCEPTED`/`REJECTED`/`ERROR`), and release cached connections via `BAQCTERM`. `[CONFIRMED — CALL-API]`

- **Input:** `IN-CLAIM-TYPE`, `IN-CLAIM-AMOUNT` from the current input message.
- **Processing:**
  1. Build `CLAIMREQ`: set `claimType`, `claimType-length` per BR-002, and `claimAmount` (converted from `9(7)V9(2)` input to `COMP-2` per BR-013).
  2. `CALL 'BAQCSTUB' USING BAQ-REQUEST-PTR BAQ-REQUEST-LEN BAQ-RESPONSE-PTR BAQ-RESPONSE-LEN BAQ-REQUEST-INFO API-STATUS-MESSAGE`. `[CONFIRMED]`
  3. Evaluate `OUT-API-STATUS-CODE` and `Xstatus2` per BR-004.
  4. `CALL 'BAQCTERM'`. `[CONFIRMED]`
  5. Populate `OUT-CLAIM-STATUS` in `OUTPUT-MSG`.
- **Output:** `OUT-CLAIM-STATUS ∈ {'ACCEPTED', 'REJECTED', 'ERROR'}` plus `OUT-MESSAGE`.
- **Acceptance Criteria:**
  - **AC-B2.1:** *Given* `OUT-API-STATUS-CODE = 0` and `Xstatus2 = 'Accepted'`, *then* `OUT-CLAIM-STATUS = 'ACCEPTED '` (padded to 10).
  - **AC-B2.2:** *Given* `OUT-API-STATUS-CODE = 0` and `Xstatus2 ≠ 'Accepted'`, *then* `OUT-CLAIM-STATUS = 'REJECTED '`.
  - **AC-B2.3:** *Given* `OUT-API-STATUS-CODE ≠ 0`, *then* `OUT-CLAIM-STATUS = 'ERROR '` and a `LOG-MESSAGE` entry containing `OUT-API-STATUS-MESSAGE` is emitted.
  - **AC-B2.4:** *Given* any path through CALL-API, *then* `BAQCTERM` is invoked exactly once per message.
  - **AC-B2.5:** *Given* `Xstatus2` is empty or its `Xstatus2-length = 0`, *then* the status is treated as non-approved (`REJECTED`) — see BR-015.

### Feature Area C — External Claims Rule API Integration

#### FR-C1 — Derive API `claimType` Length from Claim Category
**Statement:** The system shall set `claimType-length` in the outbound `CLAIMREQ` according to the claim category, defaulting unknown categories to MEDICAL. `[CONFIRMED — DO-CALL-CLAIM-RULE; CALL-API]`

- **Input:** `REQ-CLAIM-TYPE` or `IN-CLAIM-TYPE` (trimmed, uppercase comparison — see BR-014).
- **Processing:** Apply BR-002.
- **Output:** `CLAIMREQ.claimType` (string, 255 bytes, padded) and `CLAIMREQ.claimType-length` (short, S9999 COMP-5).
- **Acceptance Criteria:**
  - **AC-C1.1:** `DRUG` → `claimType-length = 4`.
  - **AC-C1.2:** `DENTAL` → `claimType-length = 6`.
  - **AC-C1.3:** `MEDICAL` → `claimType-length = 7`.
  - **AC-C1.4:** Any other value (including empty) → `claimType-length = 7`, `claimType = 'MEDICAL'`; no abend.

#### FR-C2 — Invoke z/OS Connect API Requester
**Statement:** The system shall invoke `BAQCSTUB` with a well-formed request/response/metadata parameter list and process the returned status. `[CONFIRMED]`

- **Input:** `CLAIMREQ`, `CLAIMINF` metadata, `BAQRINFO` request info structure.
- **Processing:** Execute `CALL 'BAQCSTUB'` with the six-parameter contract (see §7.4).
- **Output:** Populated `CLAIMRSP`; populated `API-STATUS-MESSAGE` (code, length, text).
- **Acceptance Criteria:**
  - **AC-C2.1:** *Given* `OUT-API-STATUS-CODE = 0`, *then* `CLAIMRSP` is parsed and response-driven status is applied per BR-003/BR-004.
  - **AC-C2.2:** *Given* `OUT-API-STATUS-CODE ≠ 0`, *then* the error path forces status to PEND (CICS) or ERROR (IMS) and invokes logging.
  - **AC-C2.3:** *Given* the API call is made, *then* `CLAIMINF` metadata (name `Sample-Node.js-Claims-Rule-API_1.0`, path `%2Fclaim%2Frule`, method `GET`) is used verbatim without runtime override. `[CONFIRMED — copybook literals]`

---

## 4. Data Model

The data model is partitioned into three clearly separated layers:

1. **Transport contracts** — payloads on CICS channels and IMS message queue.
2. **API Requester payloads** — internal COBOL structures exchanged with `BAQCSTUB`.
3. **Persistence schema** — VSAM KSDS record layout.

### 4.1 Layer 1 — Transport Contracts

#### 4.1.1 `ClaimRequestCICS` (Copybook `CLAIMRQC`, structure `REQ-CLAIM-CONTAINER`) — ~72 bytes + action `[CONFIRMED]`

| Field | COBOL PIC | Modern Type | Required | Notes |
|---|---|---|---|---|
| `REQ-CLAIM-ID` | X(8) | string(8) | yes | Business key |
| `REQ-CLAIM-TYPE` | X(8) | enum `{DRUG, DENTAL, MEDICAL}` | yes | Uppercase, trimmed |
| `REQ-CLAIM-AMOUNT` | COMP-2 | IEEE 754 double-precision binary floating point | yes | See R-04 and BR-013 |
| `REQ-CLAIM-DATE` | X(10) | date-string | yes | Expected `YYYY-MM-DD` `[INFERRED]` |
| `REQ-CLAIM-DESC` | X(21) | string(21) | no | Free text |
| `REQ-CLAIM-PROVIDER` | X(21) | string(21) | no | Free text |
| `REQ-CLAIM-ACTION` | X(1) | char enum `{S, R, U}` | yes | Drives FR-A1 |
| `REQ-FILLER` | X(4) | string(4) (reused as update-status) | conditional | Required for action `U`; carries new status value (see R-07) |

#### 4.1.2 `ClaimResponseCICS` (Copybook `CLAIMRSC`, structure `RSP-CLAIM-CONTAINER`) `[CONFIRMED]`

| Field | COBOL PIC | Modern Type | Notes |
|---|---|---|---|
| `RSP-CLAIM-ID` | X(8) | string(8) | |
| `RSP-CLAIM-TYPE` | X(8) | string(8) | |
| `RSP-CLAIM-AMOUNT` | COMP-2 | double | |
| `RSP-CLAIM-DATE` | X(10) | date-string | |
| `RSP-CLAIM-DESC` | X(21) | string(21) | |
| `RSP-CLAIM-PROVIDER` | X(21) | string(21) | |
| `RSP-CLAIM-STATUS` | X(4) | enum `{OKAY, PEND}` | See BR-003 |
| `RSP-CLAIM-CICS-RESP` | S9(8) COMP | int32 | CICS EIBRESP |
| `RSP-CLAIM-CICS-RESP2` | S9(8) COMP | int32 | CICS EIBRESP2 |
| `RSP-CLAIM-OUTPUT-MESSAGE` | X(80) | string(80) | Human-readable diagnostic |

#### 4.1.3 `ClaimMessageIMS` (Copybook `IMSCLAIC`) `[CONFIRMED]`

**Input segment `INPUT-MSG`:**

| Field | COBOL PIC | Modern Type | Notes |
|---|---|---|---|
| `IN-LL` | S9(3) COMP | int16 | IMS segment length |
| `IN-ZZ` | S9(3) COMP | int16 | IMS reserved |
| `IN-TRANCODE` | X(10) | string(10) | IMS transaction code |
| `IN-CLAIM-TYPE` | X(8) | enum (see BR-002, BR-014) | |
| `IN-CLAIM-DATE` | X(10) | date-string | |
| `IN-CLAIM-AMOUNT` | 9(7)V9(2) | fixed decimal(9,2) | Packed/display numeric — see R-04 |
| `IN-CLAIM-DESC` | X(20) | string(20) | Narrower than CICS counterpart (21) |

**Output segment `OUTPUT-MSG`:**

| Field | COBOL PIC | Modern Type | Notes |
|---|---|---|---|
| `OUT-LL` | S9(3) COMP | int16 | |
| `OUT-ZZ` | S9(3) COMP | int16 | |
| `OUT-CLAIM-TYPE` | X(8) | string(8) | |
| `OUT-CLAIM-AMOUNT` | 9(7)V9(2) | decimal(9,2) | |
| `OUT-CLAIM-DESC` | X(20) | string(20) | |
| `OUT-CLAIM-STATUS` | X(10) | enum `{ACCEPTED, REJECTED, ERROR}` | |
| `OUT-MESSAGE` | X(40) | string(40) | |

### 4.2 Layer 2 — API Requester Payloads

#### 4.2.1 `ApiRequest` (Copybook `CLAIMREQ`) `[CONFIRMED]`

| Field | COBOL PIC | Modern Type |
|---|---|---|
| `claimType-length` | S9999 COMP-5 | int16 |
| `claimType` | X(255) | string(255) |
| `claimAmount` | COMP-2 | double |

#### 4.2.2 `ApiResponse` (Copybook `CLAIMRSP`) `[CONFIRMED]`

Each business field is encoded as a triad `{num, length, value}` driven by the z/OS Connect API Requester binding.

| Group | Fields | Types |
|---|---|---|
| Claim Type | `claim-type-num`, `claim-type2-length`, `claim-type2` | int32 / int16 / string(255) |
| Amount | `amount-num`, `amount2-length`, `amount2` | int32 / int16 / string(255) |
| Status | `Xstatus-num`, `Xstatus2-length`, `Xstatus2` | int32 / int16 / string(255) |
| Reason | `reason-num`, `reason2-length`, `reason2` | int32 / int16 / string(255) |

Semantics of the `num` and `length` indicators are defined by the z/OS Connect binding generator. `[UNKNOWN — exact JSON↔COBOL mapping]`

#### 4.2.3 `ApiMetadata` (Copybook `CLAIMINF`) — Fixed Constants `[CONFIRMED]`

| Attribute | Value | COBOL Source |
|---|---|---|
| API name | `Sample-Node.js-Claims-Rule-API_1.0` | Literal |
| API name length | 34 | Literal |
| API path (URL-encoded) | `%2Fclaim%2Frule` | Literal |
| API path length | 15 | Literal |
| HTTP method | `GET` | Literal |

#### 4.2.4 `ApiStatus` (`API-STATUS-MESSAGE`, IMS) `[CONFIRMED]`

| Field | COBOL PIC | Modern Type |
|---|---|---|
| `OUT-API-STATUS-CODE` | S9(8) COMP | int32 |
| `OUT-API-STATUS-MSGLEN` | S9(8) COMP | int32 |
| `OUT-API-STATUS-MESSAGE` | X(1024) | string(1024) |

#### 4.2.5 `BaqRequestInfo` (Copybook `BAQRINFO`) `[UNKNOWN]`
Referenced by both programs and passed to `BAQCSTUB` as `BAQ-REQUEST-INFO`; internal layout is not enumerated in the available analysis artifacts. Treat as a z/OS Connect supplied opaque structure. Investigation required before modernization.

### 4.3 Layer 3 — Persistence Schema

#### 4.3.1 VSAM KSDS `CLAIMCIF`

| Property | Value | Evidence |
|---|---|---|
| Organization | VSAM KSDS | `[INFERRED — READ/WRITE/READ UPDATE/REWRITE + RIDFLD usage]` |
| Record layout | `RSP-CLAIM-CONTAINER` as defined in §4.1.2 | `[CONFIRMED]` |
| Approximate record length | ~181 bytes (8+8+8+10+21+21+4+4+4+80 fixed = 168 + alignment; confidence ±20 bytes) | `[INFERRED — summed from PIC widths]` |
| Key field | `RSP-CLAIM-ID` (X(8)) | `[INFERRED — used as RIDFLD]` |
| Key offset / length | `[UNKNOWN — requires VSAM DEFINE CLUSTER]` | |
| Operations | WRITE, READ, READ UPDATE, REWRITE | `[CONFIRMED]` |
| Duplicate key handling | KSDS uniqueness; `DFHRESP(DUPREC)` surfaced on WRITE | `[INFERRED]` |
| Retention / archival | `[UNKNOWN]` | |

### 4.4 Consolidated COBOL → Modern Attribute Map

| COBOL Field | PIC / Type | Modern Entity.Attribute | Modern Type |
|---|---|---|---|
| `REQ-CLAIM-ID` | X(8) | `ClaimRequestCICS.claimId` | string(8) |
| `REQ-CLAIM-TYPE` | X(8) | `ClaimRequestCICS.claimType` | enum |
| `REQ-CLAIM-AMOUNT` | COMP-2 | `ClaimRequestCICS.claimAmount` | double |
| `REQ-CLAIM-DATE` | X(10) | `ClaimRequestCICS.claimDate` | date-string |
| `REQ-CLAIM-DESC` | X(21) | `ClaimRequestCICS.claimDescription` | string(21) |
| `REQ-CLAIM-PROVIDER` | X(21) | `ClaimRequestCICS.claimProvider` | string(21) |
| `REQ-CLAIM-ACTION` | X(1) | `ClaimRequestCICS.action` | char enum |
| `REQ-FILLER` | X(4) | `ClaimRequestCICS.updateStatus` | string(4) |
| `RSP-CLAIM-STATUS` | X(4) | `ClaimResponseCICS.status` | enum `{OKAY, PEND}` |
| `RSP-CLAIM-CICS-RESP` | S9(8) COMP | `ClaimResponseCICS.cicsResponse` | int32 |
| `RSP-CLAIM-CICS-RESP2` | S9(8) COMP | `ClaimResponseCICS.cicsResponse2` | int32 |
| `RSP-CLAIM-OUTPUT-MESSAGE` | X(80) | `ClaimResponseCICS.message` | string(80) |
| `IN-TRANCODE` | X(10) | `ClaimMessageIMS.tranCode` | string(10) |
| `IN-CLAIM-AMOUNT` | 9(7)V9(2) | `ClaimMessageIMS.claimAmount` | decimal(9,2) |
| `OUT-CLAIM-STATUS` | X(10) | `ClaimMessageIMS.status` | enum `{ACCEPTED, REJECTED, ERROR}` |
| `claimType-length` | S9999 COMP-5 | `ApiRequest.claimTypeLength` | int16 |
| `claimAmount` (API) | COMP-2 | `ApiRequest.claimAmount` | double |
| `Xstatus2` | X(255) | `ApiResponse.status` | string(255) |
| `reason2` | X(255) | `ApiResponse.reason` | string(255) |
| `OUT-API-STATUS-CODE` | S9(8) COMP | `ApiStatus.code` | int32 |
| `OUT-API-STATUS-MESSAGE` | X(1024) | `ApiStatus.message` | string(1024) |
| `BAQ-APIPATH` | X(255) | `ApiMetadata.path` | string(255) |

---

## 5. Process Flows

### 5.1 CLAIMCI0 — CICS Online Transaction

```
START
 ├─ DO-INITIALIZATION
 │    └─ Initialize REQUEST / RESPONSE / API-INFO; set file name 'CLAIMCIF'
 ├─ DO-MAIN-CONTROL
 │    ├─ EXEC CICS ASSIGN CHANNEL  → if abnormal: log + return error
 │    ├─ STARTBROWSE CONTAINER / GETNEXT / GET CONTAINER (input)
 │    └─ EVALUATE REQ-CLAIM-ACTION
 │         ├─ 'S' → DO-SUBMIT-CLAIM-REC
 │         │        ├─ Copy REQ-* → RSP-*
 │         │        ├─ DO-CALL-CLAIM-RULE → BAQCSTUB
 │         │        │     ├─ Map type → length (BR-002)
 │         │        │     ├─ If API OK + Xstatus2='Accepted' → RSP-STATUS='OKAY'
 │         │        │     └─ Else → RSP-STATUS='PEND' + CSMT log
 │         │        └─ EXEC CICS WRITE FILE('CLAIMCIF')
 │         ├─ 'R' → DO-READ-CLAIM-REC
 │         │        └─ EXEC CICS READ FILE('CLAIMCIF')
 │         ├─ 'U' → DO-UPDATE-CLAIM-REC
 │         │        ├─ EXEC CICS READ FILE('CLAIMCIF') UPDATE
 │         │        └─ If success → DO-REWRITE-CLAIM-REC → EXEC CICS REWRITE
 │         └─ other → set unknown-operation message
 ├─ DO-RETURN-TO-CICS
 │    ├─ PUT CONTAINER (response)
 │    └─ EXEC CICS RETURN
 └─ Any error path → DO-WRITE-TO-CSMT (timestamp + text)
```
`[CONFIRMED — procedure paragraphs and CICS verbs]`

### 5.2 IMSCLAIM — IMS Message Processing Loop

```
ENTRY (PROCEDURE DIVISION USING IO-PCB-MASK)
 └─ DO-MAIN LOOP:
      ├─ GET-INPUT-MESSAGE → CALL 'CBLTDLI' USING GU
      │     ├─ PCB-STATUS = 'QC'      → EXIT LOOP (normal end, BR-006)
      │     └─ PCB-STATUS ≠ space,'QC' → LOG-MESSAGE + EXIT
      ├─ CALL-API:
      │     ├─ Build CLAIMREQ (claimType-length per BR-002; claimAmount per BR-013)
      │     ├─ CALL 'BAQCSTUB' (§7.4)
      │     ├─ If OUT-API-STATUS-CODE = 0:
      │     │     ├─ Xstatus2 = 'Accepted' → OUT-CLAIM-STATUS='ACCEPTED'
      │     │     └─ else                   → OUT-CLAIM-STATUS='REJECTED'
      │     ├─ Else → OUT-CLAIM-STATUS='ERROR' + LOG-MESSAGE
      │     └─ CALL 'BAQCTERM'
      └─ SET-OUTPUT-MESSAGE → CALL 'CBLTDLI' USING ISRT
RETURN to IMS
```
`[CONFIRMED]`

### 5.3 Decision Points Summary

| Decision | Program / Paragraph | True Path | False Path |
|---|---|---|---|
| Channel assigned and container present? | CLAIMCI0 / DO-MAIN-CONTROL | Continue to EVALUATE | Log + return error (FR-A1 AC5) |
| `REQ-CLAIM-ACTION` ∈ {S, R, U}? | CLAIMCI0 / DO-MAIN-CONTROL | Dispatch handler | Unknown-operation response |
| API `Xstatus2` exact-match `'Accepted'`? | DO-CALL-CLAIM-RULE / CALL-API | Status OKAY or ACCEPTED | Status PEND or REJECTED |
| `OUT-API-STATUS-CODE = 0`? | CALL-API | Map Xstatus2 | Status PEND / ERROR + log |
| `READ UPDATE` succeeded? | DO-UPDATE-CLAIM-REC | REWRITE | Skip rewrite, error message |
| `PCB-STATUS = 'QC'`? | IMSCLAIM / DO-MAIN | Exit loop | Continue loop (if space) or log+exit |

---

## 6. Business Rules

Each rule carries: statement, type, verification method, and source traceability.

| ID | Statement | Type | Verification Method | Source | Evidence |
|---|---|---|---|---|---|
| **BR-001** | The CICS program shall route by action code: `'S'`=Submit, `'R'`=Read, `'U'`=Update. Any other value returns an unknown-operation response with no file I/O. | Routing | Unit test per action + negative case | `CLAIMCI0.DO-MAIN-CONTROL` | `[CONFIRMED]` |
| **BR-002** | `claimType-length` in `CLAIMREQ` shall be set as: DRUG=4, DENTAL=6, MEDICAL=7. Any other type (including empty) defaults to MEDICAL (7). | Mapping | Parameterized test: 4 inputs → 4 expected lengths | `DO-CALL-CLAIM-RULE`; `CALL-API` | `[CONFIRMED]` |
| **BR-003** | A claim is approved only if `Xstatus2` equals the exact literal `"Accepted"` (case-sensitive, leading/trailing spaces trimmed). CICS maps to `'OKAY'`; otherwise `'PEND'`. | Decision | Equivalence-class + boundary test including case variants | `DO-CALL-CLAIM-RULE` | `[CONFIRMED]` |
| **BR-004** | In IMS: approved → `OUT-CLAIM-STATUS='ACCEPTED'`; successful API with other `Xstatus2` → `'REJECTED'`; API/stub failure (`OUT-API-STATUS-CODE ≠ 0`) → `'ERROR'`. | Decision | State-table test; 3 outcome classes | `CALL-API` | `[CONFIRMED]` |
| **BR-005** | A `REWRITE` shall occur only after a successful `READ … UPDATE` on `CLAIMCIF` (lock held). Failed READ UPDATE must skip REWRITE. | Concurrency | Concurrent-transaction test and failure-injection test | `DO-UPDATE-CLAIM-REC → DO-REWRITE-CLAIM-REC` | `[CONFIRMED]` |
| **BR-006** | The IMS program shall loop until IO-PCB status = `'QC'` (normal end-of-messages) or a non-space, non-`'QC'` status (abnormal). | Control flow | Loop test with N messages + QC terminator; fault-injection for non-QC statuses | `IMSCLAIM.DO-MAIN` | `[CONFIRMED]` |
| **BR-007** | On API or stub failure, the program shall force a non-approval status (CICS: PEND; IMS: ERROR) and log a CSMT or DISPLAY entry. An API/stub failure alone shall not cause a COBOL runtime abend. This rule does not guarantee absence of abend from unrelated runtime errors (e.g., S0C4). | Resilience | Fault-injection test: stub returns non-zero code → assert status + log | `DO-CALL-CLAIM-RULE`; `CALL-API` | `[INFERRED — narrowed from original claim]` |
| **BR-008** | The IMS program shall call `BAQCTERM` after each API invocation to release cached requester connections. | Resource lifecycle | Code-path coverage: every CALL-API exit reaches BAQCTERM | `IMSCLAIM.CALL-API` | `[CONFIRMED]` |
| **BR-009** | The CICS program shall persist every submitted claim (including PEND outcomes) to `CLAIMCIF` and return CICS RESP/RESP2 codes in the response. | Persistence | Integration test inspecting VSAM after each outcome class | `CLAIMCI0.DO-SUBMIT-CLAIM-REC` | `[CONFIRMED]` |
| **BR-010** | CSMT log entries shall be prefixed with a formatted timestamp derived from CICS `ASKTIME`/`FORMATTIME`. | Observability | Log-format regression test | `CLAIMCI0.DO-WRITE-TO-CSMT` | `[CONFIRMED]` |
| **BR-011** | API metadata — name `Sample-Node.js-Claims-Rule-API_1.0`, path `/claim/rule` (URL-encoded `%2Fclaim%2Frule`), method `GET` — is fixed at compile time and must match the deployed z/OS Connect service. | Configuration | Contract test vs z/OS Connect service catalog | Copybook `CLAIMINF` | `[CONFIRMED]` |
| **BR-012** | On Update, the mutable field is the claim status (`RSP-CLAIM-STATUS`), sourced from `REQ-FILLER` in the inbound container. Mutability of other fields (type, amount, description, provider) is `[UNKNOWN]` and must be explicitly defined before any modernization. | Data integrity | Field-diff test: before vs after REWRITE | `DO-REWRITE-CLAIM-REC` | `[INFERRED]` |
| **BR-013** | `claimAmount` on the API request is transmitted as IEEE 754 double (`COMP-2`). Conversion from IMS `9(7)V9(2)` fixed decimal to COMP-2 shall preserve two decimal places; IEEE rounding (round-half-to-even) applies. Values outside the range ±9 999 999.99 are rejected with status ERROR. | Data integrity | Boundary tests at max/min and common decimal values (0.01, 0.10, 1.23, 999999.99) | `CALL-API`; `DO-CALL-CLAIM-RULE` | `[INFERRED]` |
| **BR-014** | Claim-type comparison for BR-002 shall be performed on the trimmed, uppercased value of `REQ-CLAIM-TYPE` / `IN-CLAIM-TYPE`. Mixed-case inputs (e.g., `"Dental"`) classify correctly; the API request still carries the canonical value (`DRUG`/`DENTAL`/`MEDICAL`). | Normalization | Case-matrix test: lower/mixed/upper | Current analysis | `[INFERRED — clarification of BR-002]` |
| **BR-015** | If `Xstatus2-length = 0`, `Xstatus2` is absent, or `reason2` is inconsistent with `reason2-length`, the decision shall be treated as non-approval (PEND / REJECTED) and a log entry emitted. | Defensive parsing | Malformed-payload fault injection | Current analysis | `[INFERRED]` |
| **BR-016** | Resubmission of a claim with an existing `claimId` shall not silently overwrite the prior record. The Submit path relies on VSAM KSDS uniqueness: `DFHRESP(DUPREC)` surfaces as a duplicate-key response and the caller must use action `'U'` to modify. | Idempotency | Duplicate-submit test | `CLAIMCI0.DO-SUBMIT-CLAIM-REC` | `[INFERRED — from KSDS + absence of UPSERT logic]` |
| **BR-017** | Width differences across channels must not silently truncate free-text fields: CICS description = 21 bytes; IMS description = 20 bytes; CICS status = 4 bytes; IMS status = 10 bytes; CICS message = 80 bytes; IMS message = 40 bytes. Any cross-channel convergence requires explicit mapping with truncation rules. | Data integrity | Cross-channel integration test | Copybooks `CLAIMRQC`, `CLAIMRSC`, `IMSCLAIC` | `[CONFIRMED]` |

### 6.1 Business Rule Verification Matrix

| BR | Test ID | Inputs | Expected Output | Evidence |
|---|---|---|---|---|
| BR-002 | T-BR002-a | `REQ-CLAIM-TYPE='DRUG'` | `claimType-length=4` | `[CONFIRMED]` |
| BR-002 | T-BR002-b | `'DENTAL'` | `claimType-length=6` | `[CONFIRMED]` |
| BR-002 | T-BR002-c | `'MEDICAL'` | `claimType-length=7` | `[CONFIRMED]` |
| BR-002 | T-BR002-d | `'VISION'` | `claimType-length=7`, `claimType='MEDICAL'` | `[CONFIRMED]` |
| BR-003 | T-BR003-a | `Xstatus2='Accepted'` + OK code | `RSP-CLAIM-STATUS='OKAY'` | `[CONFIRMED]` |
| BR-003 | T-BR003-b | `Xstatus2='ACCEPTED'` | `RSP-CLAIM-STATUS='PEND'` | `[CONFIRMED]` |
| BR-003 | T-BR003-c | `Xstatus2='accepted'` | `RSP-CLAIM-STATUS='PEND'` | `[CONFIRMED]` |
| BR-004 | T-BR004-a | Code=0, `Xstatus2='Accepted'` | `OUT-CLAIM-STATUS='ACCEPTED'` | `[CONFIRMED]` |
| BR-004 | T-BR004-b | Code=0, `Xstatus2='Denied'` | `OUT-CLAIM-STATUS='REJECTED'` | `[CONFIRMED]` |
| BR-004 | T-BR004-c | Code=12 | `OUT-CLAIM-STATUS='ERROR'` + log | `[CONFIRMED]` |
| BR-005 | T-BR005-a | READ UPDATE fails NOTFND | No REWRITE; error message | `[CONFIRMED]` |
| BR-005 | T-BR005-b | Two concurrent updates | Second waits/LOCKED per VSAM | `[INFERRED]` |
| BR-013 | T-BR013-a | IMS amount `0000001.23` | API `claimAmount=1.23` (double) | `[INFERRED]` |
| BR-013 | T-BR013-b | IMS amount `9999999.99` | API `claimAmount=9999999.99` | `[INFERRED]` |
| BR-015 | T-BR015-a | `Xstatus2-length=0` | PEND / REJECTED + log | `[INFERRED]` |
| BR-016 | T-BR016-a | Submit existing claimId | `DFHRESP(DUPREC)`; error message | `[INFERRED]` |

---

## 7. External Interfaces

### 7.1 Inbound Interfaces

#### 7.1.1 CICS Channel/Container (CLAIMCI0)
- **Protocol / Mechanism:** CICS API verbs `ASSIGN CHANNEL`, `STARTBROWSE CONTAINER`, `GETNEXT CONTAINER`, `GET CONTAINER`. `[CONFIRMED]`
- **Input structure:** `REQ-CLAIM-CONTAINER` (Copybook `CLAIMRQC`, §4.1.1).
- **Container naming:** `[UNKNOWN]` — channel and container names are not literalized in the visible source; must be documented from CICS resource definitions.
- **Versioning strategy:** The container carries no version field. Recommend introducing a leading `REQ-VERSION` field (e.g., X(4)) in a future revision and using container naming suffixes for v2+. `[INFERRED — current design lacks versioning]`

#### 7.1.2 IMS Message Queue (IMSCLAIM)
- **Protocol / Mechanism:** IMS DL/I via `CBLTDLI` with function codes `GU`, `GN`, `ISRT`. `[CONFIRMED]`
- **Input structure:** `INPUT-MSG` (Copybook `IMSCLAIC`, §4.1.3).
- **Transaction code:** Carried in `IN-TRANCODE`; specific value `[UNKNOWN]`.
- **Versioning strategy:** The segment `IN-ZZ` reserved field may be used to carry a version marker. Currently unused for versioning. `[INFERRED]`

### 7.2 Outbound Interfaces

#### 7.2.1 Claims Rule REST API (via z/OS Connect)
- **Protocol:** HTTP `GET` through z/OS Connect V3 API Requester. `[CONFIRMED]`
- **Endpoint:** Name `Sample-Node.js-Claims-Rule-API_1.0`, path `/claim/rule` (URL-encoded `%2Fclaim%2Frule`).
- **Request payload:** `CLAIMREQ` serialized per z/OS Connect mapping; fields `claimType` (string), `claimAmount` (double). `[CONFIRMED]`
- **Response payload:** `CLAIMRSP` with `{claim-type2, amount2, Xstatus2, reason2}` triads. `[CONFIRMED]`
- **Authentication / TLS:** `[UNKNOWN]` — not visible in program source; handled by z/OS Connect configuration.
- **Timeout and retry:** None implemented in COBOL; caller receives whatever `BAQCSTUB` surfaces. `[CONFIRMED by absence]`

#### 7.2.2 Response Publishing
- **CICS (CLAIMCI0):** `EXEC CICS PUT CONTAINER` + `EXEC CICS RETURN` with `RSP-CLAIM-CONTAINER`. `[CONFIRMED]`
- **IMS (IMSCLAIM):** `CALL 'CBLTDLI' USING ISRT, IO-PCB-MASK, OUTPUT-MSG`. `[CONFIRMED]`

#### 7.2.3 Connection Cleanup (IMS Only)
- **Mechanism:** Native COBOL `CALL 'BAQCTERM'` with no parameters, invoked once per message. `[CONFIRMED]`

### 7.3 Data Store Interfaces

| Store | Type | Program | Operations | Evidence |
|---|---|---|---|---|
| `CLAIMCIF` | VSAM KSDS | `CLAIMCI0` | WRITE, READ, READ UPDATE, REWRITE | `[CONFIRMED]` |
| `CSMT` | CICS Transient Data Queue | `CLAIMCI0` | WRITEQ TD | `[CONFIRMED]` |
| IMS Queue | IMS Message Queue | `IMSCLAIM` | GU, GN, ISRT | `[CONFIRMED]` |

### 7.4 `BAQCSTUB` Call Contract `[CONFIRMED]`

| Parameter | Direction | Type | Purpose |
|---|---|---|---|
| `BAQ-REQUEST-PTR` | In | Pointer | Address of `CLAIMREQ` |
| `BAQ-REQUEST-LEN` | In | S9(9) COMP-5 (int32) | Length of request buffer |
| `BAQ-RESPONSE-PTR` | In/Out | Pointer | Address of `CLAIMRSP` buffer |
| `BAQ-RESPONSE-LEN` | In/Out | S9(9) COMP-5 (int32) | Length of response buffer (in: capacity; out: populated length) |
| `BAQ-REQUEST-INFO` | In | `BAQRINFO` structure | API metadata (from `CLAIMINF`) |
| `API-STATUS-MESSAGE` | Out | 1024-byte text + code + length | Diagnostic status |

### 7.5 Field-Level Constraints

| Field | Constraint |
|---|---|
| `REQ-CLAIM-ID` | Fixed 8 bytes; no embedded null; trimmed for key compare. |
| `REQ-CLAIM-TYPE` / `IN-CLAIM-TYPE` | Compared uppercase-trimmed (BR-014); enum `{DRUG, DENTAL, MEDICAL}` |
| `REQ-CLAIM-AMOUNT` | COMP-2; see BR-013 for precision/rounding |
| `IN-CLAIM-AMOUNT` | `9(7)V9(2)`; range 0.00 – 9 999 999.99 |
| `REQ-CLAIM-ACTION` | `'S'`, `'R'`, `'U'` only; all other values produce unknown-operation response |
| `RSP-CLAIM-STATUS` | `'OKAY'` or `'PEND'`, left-justified, padded |
| `OUT-CLAIM-STATUS` | `'ACCEPTED'`, `'REJECTED'`, or `'ERROR'`, left-justified, padded to 10 |
| `Xstatus2` | Up to 255 bytes; significant length in `Xstatus2-length` |

---

## 8. Non-Functional Requirements

Targets are proposed based on typical enterprise CICS/IMS online-transaction profiles. Where no analyzable basis exists, the value is proposed as an initial target and flagged `[UNKNOWN — confirm with business]`.

### 8.1 Performance

| ID | Requirement | Target | Evidence / Basis |
|---|---|---|---|
| NFR-P1 | End-to-end latency of `CLAIMCI0` for a Submit/Read/Update request, excluding external API time. | p95 ≤ 200 ms, p99 ≤ 500 ms | `[UNKNOWN — proposed target]` |
| NFR-P2 | External API round-trip budget for `BAQCSTUB`. | p95 ≤ 1 500 ms | `[UNKNOWN — proposed target]` |
| NFR-P3 | End-to-end latency per IMS message in `IMSCLAIM` (including API). | p95 ≤ 2 000 ms | `[UNKNOWN — proposed target]` |
| NFR-P4 | API-call count per claim decision. | exactly 1 | `[CONFIRMED]` |

### 8.2 Throughput and Scalability

| ID | Requirement | Target | Basis |
|---|---|---|---|
| NFR-T1 | Sustained CICS Submit throughput. | 100 TPS per CICS region under nominal load | `[UNKNOWN — proposed]` |
| NFR-T2 | IMS message processing rate. | 50 messages/second per MPR | `[UNKNOWN — proposed]` |
| NFR-T3 | Horizontal scaling via additional CICS/IMS regions. | Linear scaling up to 4 regions | `[UNKNOWN]` |

### 8.3 Availability & Reliability

| ID | Requirement | Target | Basis |
|---|---|---|---|
| NFR-A1 | Platform availability during business hours. | 99.9% | `[UNKNOWN — proposed]` |
| NFR-A2 | RTO for regional failure. | ≤ 1 hour | `[UNKNOWN]` |
| NFR-A3 | RPO for `CLAIMCIF`. | ≤ 15 minutes | `[UNKNOWN]` |
| NFR-A4 | Graceful degradation on API failure: PEND (CICS) or ERROR (IMS) per BR-007. | 100% of API/stub non-zero codes handled without application abend | `[CONFIRMED — BR-007 scope]` |
| NFR-A5 | API timeout budget in z/OS Connect. | 5 000 ms default; configurable | `[UNKNOWN — must be set in z/OS Connect]` |
| NFR-A6 | No retry is currently performed in the COBOL layer. Retry strategy, if introduced, must be idempotent and bounded. | 0 retries today; target ≤ 2 retries with exponential backoff when introduced | `[CONFIRMED for current state]` |

### 8.4 Security

| ID | Requirement | Target | Basis |
|---|---|---|---|
| NFR-S1 | AuthN for inbound CICS transactions. | RACF/ACF2/Top Secret user via CICS | `[UNKNOWN — proposed]` |
| NFR-S2 | AuthZ per transaction code. | Role-based; enforce at CICS transaction level | `[UNKNOWN]` |
| NFR-S3 | TLS for outbound API Requester calls. | TLS 1.2+ enforced via AT-TLS or z/OS Connect keystore | `[UNKNOWN]` |
| NFR-S4 | Data-at-rest protection for `CLAIMCIF`. | VSAM encryption (z/OS Data Set Encryption) | `[UNKNOWN]` |
| NFR-S5 | Audit logging for every submit/update. | 100% coverage with user ID and timestamp | `[UNKNOWN — current logging lacks user ID; must be added]` |
| NFR-S6 | PII/PHI handling for claim description. | Mask or omit in non-production environments | `[UNKNOWN]` |

### 8.5 Observability

| ID | Requirement | Target | Basis |
|---|---|---|---|
| NFR-O1 | Log coverage for error paths. | 100% of API/file error branches produce a log line | `[CONFIRMED — required by BR-007, BR-010]` |
| NFR-O2 | Correlation ID propagation. | Accept inbound correlation ID; include in CSMT log and in outbound API call | `[UNKNOWN — not present today; must be added]` |
| NFR-O3 | Alert thresholds. | Alert on ≥ 1% ERROR rate over 5 minutes; ≥ 5% PEND rate over 15 minutes | `[UNKNOWN — proposed]` |
| NFR-O4 | Log retention. | ≥ 90 days online; 7 years archive (healthcare regulatory expectation) | `[UNKNOWN — must be confirmed with compliance]` |

### 8.6 Testability

| ID | Requirement | Target | Basis |
|---|---|---|---|
| NFR-Q1 | Automated unit-test coverage of paragraphs. | ≥ 80% | Proposed |
| NFR-Q2 | Business-rule coverage. | 100% of BR-001…BR-017 covered by at least one automated test | Proposed |
| NFR-Q3 | Contract tests against Claims Rule API. | Consumer-driven contract maintained and run in CI | Proposed |
| NFR-Q4 | Environment parity. | Dev/test/stage use the same BAQ copybooks and z/OS Connect versions | Proposed |

### 8.7 Compatibility and Portability

| ID | Requirement | Target | Basis |
|---|---|---|---|
| NFR-C1 | CICS TS level. | CICS TS 5.5+ with channel/container support | `[INFERRED]` |
| NFR-C2 | IMS level. | IMS 14+ | `[INFERRED]` |
| NFR-C3 | z/OS Connect level. | V3.0+ (matches BAQ interface) | `[CONFIRMED]` |
| NFR-C4 | Floating-point portability. | All COMP-2 values processed on z/Architecture IEEE binary FP; modernization must replace with decimal | `[CONFIRMED — risk R-04]` |

### 8.8 Legacy Constraints (Explicit)
- Fixed compile-time API metadata (no runtime override). `[CONFIRMED]`
- Case-sensitive exact match on `Xstatus2`. `[CONFIRMED]`
- No retry / no circuit breaker in COBOL layer. `[CONFIRMED]`
- No correlation/trace ID in logs. `[CONFIRMED — by absence]`
- COMP-2 and fixed decimal co-exist across channels. `[CONFIRMED]`

---

## 9. Risks & Mitigations

Each risk is rated HIGH / MEDIUM / LOW and paired with mitigation, owner role, trigger, monitoring indicator, residual risk, and contingency.

| # | Risk | Evidence | Rating & Justification | Mitigation | Owner | Trigger | Monitoring Indicator | Residual | Contingency |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | **Hardcoded API metadata** in `CLAIMINF` requires recompile to change. | `[CONFIRMED]` | HIGH — any endpoint change needs program rebuild. | Externalize metadata to a configuration container/dataset loaded at program initialization; or migrate to z/OS Connect service alias abstraction. | Platform Architect | Endpoint rename, version bump, or path relocation. | Deployment frequency of CLAIMINF changes; failed API contract tests. | LOW after externalization. | Emergency recompile + CICS NEWCOPY; keep rollback copybook archived. |
| R-02 | **Case-sensitive `"Accepted"` literal** controls approval (BR-003). | `[CONFIRMED]` | HIGH — a minor API wording shift silently rejects all claims. | Normalize comparison to uppercase-trimmed; add BR-015 defensive parsing; pin Accepted value by API contract test. | Development Lead | API version change. | % PEND/REJECTED rate spike > 20% vs baseline. | LOW after normalization. | Alert + manual re-decision sweep script. |
| R-03 | **Unknown claim types default to MEDICAL** (BR-002). | `[CONFIRMED]` | MEDIUM — misclassification risk, no rejection. | Add explicit validation; optional hard-fail mode; log defaulted classifications. | Product Owner (business policy) + Development Lead | Introduction of new claim category. | Count of defaulted-to-MEDICAL events per day. | MEDIUM. | Reprocess affected records after rule update. |
| R-04 | **Precision mismatch**: COMP-2 (CICS/API) vs `9(7)V9(2)` (IMS). | `[CONFIRMED]` | HIGH — floating-point rounding can cause financial discrepancy. | Enforce BR-013 rounding; add conversion unit tests; consider migrating API contract to decimal string or fixed-point integer cents. | Data Architect | New high-value or high-precision claim categories. | Count of amount round-trip discrepancies > 0.01. | MEDIUM. | Dual-write reconciliation batch. |
| R-05 | **Minimal error-path detail** for channel/container validation, GETNEXT, PUT CONTAINER failures. | `[INFERRED]` | MEDIUM — possible unhandled CICS exceptions. | Code review to add explicit `RESP`/`RESP2` capture on every EXEC CICS verb; add negative-path unit tests. | Development Lead | Any CICS resource (channel, container, file) outage. | Unlogged CICS abends reported by CICS region. | LOW after hardening. | CICS abend handler + CSMT dump. |
| R-06 | **No persisted decision rationale** (`reason2` not stored in `CLAIMCIF`). | `[INFERRED]` | HIGH — compliance/audit gap in regulated healthcare context. | Extend `RSP-CLAIM-CONTAINER` and VSAM schema to include `reason` (string(255)); version record layout. | Compliance Officer + Data Architect | Regulatory audit request. | Audit finding count. | MEDIUM. | Query API log archive for historical reason text. |
| R-07 | **Update status sourced from `REQ-FILLER`** — semantically ambiguous. | `[CONFIRMED]` | MEDIUM — caller confusion and fragility to copybook changes. | Rename `REQ-FILLER` to `REQ-UPDATE-STATUS` in next copybook version; update callers. | Development Lead | Any copybook revision. | Copybook diff review findings. | LOW after rename. | Dual-copybook compatibility window. |
| R-08 | **Tight coupling to `BAQCSTUB`/`BAQCTERM`**. | `[CONFIRMED]` | MEDIUM — limits portability. | Wrap BAQ calls in a thin subprogram; allow substitution with an HTTP client or message broker stub in non-mainframe targets. | Platform Architect | z/OS Connect version upgrade or replacement. | z/OS Connect deprecation notices. | MEDIUM. | Keep abstraction layer version-pinned. |
| R-09 | **Duplicate key on submit** surfaces only a generic CICS error. | `[INFERRED]` | MEDIUM — caller UX suffers; idempotency unclear. | Implement BR-016 explicit duplicate-detection message; document Submit-then-Update pattern. | Development Lead | Client retries on timeout. | DUPREC count in CSMT. | LOW. | Provide client guidance on idempotency keys. |
| R-10 | **Limited security context**: no user-id authorization inside the program. | `[INFERRED]` | HIGH — sensitive health data relies entirely on infrastructure. | Capture `EIBUSER`; add CICS security check per action; log user ID in CSMT. | Security Architect | Compliance audit; new data-sharing requirement. | Unauthorized-access incidents. | MEDIUM. | Tighten CICS transaction-level RACF rules. |
| R-11 | **Width mismatch between CICS and IMS channels**. | `[CONFIRMED]` | MEDIUM — silent truncation if channels converge. | Enforce BR-017 explicit mapping; block cross-channel data sharing until mapping is codified. | Data Architect | Consolidation project. | Truncation diff tests. | LOW. | Canonical internal schema with explicit adapters. |
| R-12 | **No retry / no circuit breaker** for transient API failures. | `[CONFIRMED]` | MEDIUM — transient outages become permanent rejects. | Introduce retry in z/OS Connect or a COBOL wrapper with capped attempts and backoff; add idempotency key. | Platform Architect | API SLO breach. | Transient-error rate > 2% / 5 min. | MEDIUM. | Offline re-decision batch job. |
| R-13 | **Repository root lacks source** — scope limited to `source/cobol`. | `[CONFIRMED]` | LOW — scope boundary confirmed. | None required; confirm periodically. | — | — | — | LOW. | — |
| R-14 | **`BAQRINFO` copybook internal layout unknown**. | `[CONFIRMED — reference only]` | MEDIUM — opaque dependency. | Request copybook from z/OS Connect team; document fields. | Platform Architect | Any BAQ upgrade. | Compile errors on z/OS Connect upgrade. | LOW after documentation. | Pin BAQ version. |
| R-15 | **Cutover data-format risk** between CICS and IMS paths during modernization. | `[INFERRED]` | HIGH — mid-migration financial or classification drift. | Dual-run with reconciliation; canonical schema; checksums on amount + type. | Migration Lead | Migration window. | Daily reconciliation variance count. | MEDIUM. | Freeze dual-run; revert to legacy path. |
| R-16 | **External API latency spikes** could cause IMS backlog or CICS timeouts. | `[CONFIRMED — absence of timeout handling]` | HIGH — queue growth and SLA breach. | Set NFR-A5 timeout; add shed-load policy in IMS; alert on queue depth. | SRE / Operations | API provider degradation. | IMS queue depth > threshold; API p95 > budget. | MEDIUM. | Pend-by-default mode until API recovers. |
| R-17 | **VSAM KSDS key definition not in scope** — design statements assume 8-byte key. | `[CONFIRMED — UNKNOWN key definition]` | LOW — operational; must be confirmed. | Retrieve VSAM DEFINE CLUSTER; record in design package. | Storage Admin | Any VSAM reorg. | DEFINE review checklist. | LOW. | Maintain authoritative cluster definition. |

---

## Appendix A — Traceability Matrix

| Requirement | COBOL Source | Evidence |
|---|---|---|
| FR-A1 | `CLAIMCI0.DO-MAIN-CONTROL`, `EVALUATE REQ-CLAIM-ACTION` | `[CONFIRMED]` for S/R/U dispatch; `[INFERRED]` for unknown-operation wording |
| FR-A2 | `CLAIMCI0.DO-SUBMIT-CLAIM-REC`, `DO-CALL-CLAIM-RULE`, `EXEC CICS WRITE FILE('CLAIMCIF')` | `[CONFIRMED]` |
| FR-A3 | `CLAIMCI0.DO-READ-CLAIM-REC`, `EXEC CICS READ` | `[CONFIRMED]` |
| FR-A4 | `CLAIMCI0.DO-UPDATE-CLAIM-REC`, `DO-REWRITE-CLAIM-REC` | `[CONFIRMED]` |
| FR-A5 | `CLAIMCI0.DO-WRITE-TO-CSMT`, `EXEC CICS ASKTIME/FORMATTIME/WRITEQ TD` | `[CONFIRMED]` |
| FR-B1 | `IMSCLAIM.DO-MAIN`, `GET-INPUT-MESSAGE`, `SET-OUTPUT-MESSAGE` | `[CONFIRMED]` |
| FR-B2 | `IMSCLAIM.CALL-API`, calls to `BAQCSTUB` and `BAQCTERM` | `[CONFIRMED]` |
| FR-C1 | `DO-CALL-CLAIM-RULE`, `CALL-API` — claim-type length mapping | `[CONFIRMED]` |
| FR-C2 | `CALL 'BAQCSTUB'` in both programs; copybooks `CLAIMINF`, `BAQRINFO` | `[CONFIRMED]` |
| BR-001 | `EVALUATE REQ-CLAIM-ACTION` | `[CONFIRMED]` |
| BR-002 | Length-set logic in `DO-CALL-CLAIM-RULE` and `CALL-API` | `[CONFIRMED]` |
| BR-003 | `IF Xstatus2 = 'Accepted'` branches | `[CONFIRMED]` |
| BR-004 | IMS `IF`/`EVALUATE` on API code + Xstatus2 | `[CONFIRMED]` |
| BR-005 | `EXEC CICS READ … UPDATE` guarding `REWRITE` | `[CONFIRMED]` |
| BR-006 | `PERFORM UNTIL PCB-STATUS = 'QC'` | `[CONFIRMED]` |
| BR-007 | Error branches in `DO-CALL-CLAIM-RULE` and `CALL-API` | `[INFERRED — narrowed]` |
| BR-008 | `CALL 'BAQCTERM'` after API block | `[CONFIRMED]` |
| BR-009 | `EXEC CICS WRITE FILE('CLAIMCIF')` after status set | `[CONFIRMED]` |
| BR-010 | `ASKTIME/FORMATTIME` + CSMT write | `[CONFIRMED]` |
| BR-011 | Copybook `CLAIMINF` literals | `[CONFIRMED]` |
| BR-012 | `DO-REWRITE-CLAIM-REC` uses `REQ-FILLER` | `[INFERRED]` |
| BR-013 | Implicit in COMP-2 usage and IMS display numeric | `[INFERRED]` |
| BR-014 | Implicit normalization for BR-002 comparisons | `[INFERRED]` |
| BR-015 | Defensive handling not present in source — requires implementation | `[INFERRED]` |
| BR-016 | Implicit via VSAM KSDS uniqueness | `[INFERRED]` |
| BR-017 | Copybook PIC widths | `[CONFIRMED]` |

---

## Appendix B — Open Questions (`[UNKNOWN]` items requiring resolution)

1. VSAM KSDS `CLAIMCIF` cluster definition: key offset/length, record size, CI/CA sizes, share options, RLS status.
2. SLAs for online response latency and IMS throughput — business-confirmed targets for NFR-P1…P3, NFR-T1…T3.
3. JSON ↔ COBOL mapping rules for `CLAIMRSP` `{num, length, value}` triads generated by z/OS Connect.
4. Security model: user authentication/authorization inside CICS/IMS, TLS configuration, credentials to Claims Rule API.
5. Retention and archival policy for `CLAIMCIF` and CSMT logs.
6. Full internal layout of `BAQRINFO` copybook.
7. Container and channel naming conventions for CLAIMCI0 inbound requests.
8. IMS transaction code bound to `IMSCLAIM` and PSB/DBD definitions.
9. Expected error-path behavior for `PUT CONTAINER` and CSMT write failures.
10. Exact wording of standard `RSP-CLAIM-OUTPUT-MESSAGE` strings (unknown-operation, not-found, duplicate, etc.).
11. Concurrency policy for `READ UPDATE` contention — wait vs LOCKED handling and caller retry expectations.
12. Correlation-ID propagation path from upstream callers to CSMT and to z/OS Connect.
13. Mutability policy for Update action beyond `RSP-CLAIM-STATUS` (BR-012).
14. Compliance retention window for audit artifacts (HIPAA, state-level healthcare requirements).

---

**End of PRD v2.0**