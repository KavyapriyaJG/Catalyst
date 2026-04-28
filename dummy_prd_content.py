DUMMY_PRD_TEXT = """# Product Requirements Document (PRD)
## CobolCraft — Minecraft-Compatible Game Server and Code Generation Toolchain

---

## 1. Executive Summary

### 1.1 Product Overview
CobolCraft is a Minecraft Java Edition-compatible multiplayer game server implemented in COBOL, paired with a code-generation toolchain that emits COBOL source from Minecraft's upstream data reports and templates. The repository is organized into three tracks: a runtime server (`src/`), a build-time code generator (`codegen/`), and a test harness (`tests/`). [CONFIRMED]

### 1.2 Business Domain
Online multiplayer sandbox voxel gaming. The server targets Minecraft Java Edition **protocol 769 / game version 1.21.4** as fixed constants (`DD-VERSION`). [CONFIRMED]

### 1.3 System Purpose
The system shall:
- Accept player connections and maintain a persistent voxel world. [CONFIRMED — `Players-Connect`, `src/world`]
- Process gameplay events including block changes, inventory and crafting, entity ticks, commands, and chat. [CONFIRMED — respective subsystems]
- Persist world, chunk, entity, and player state to region, entity, and player-data files using NBT payloads, gzip-compressed where applicable. [CONFIRMED — `World-SaveChunk`, `Players-SavePlayer`]
- Generate protocol, registry, item, and block-loot-table COBOL source at build time from upstream JSON reports. [CONFIRMED — `CodegenMain` and generators]
- Validate implementation behavior through a self-checking test framework. [CONFIRMED — `tests/test.cob`, `TestMain`]

### 1.4 Scope
This PRD defines business-facing functional, data, process, and non-functional requirements derived from static analysis of the source repository. Implementation internals are referenced via original program, paragraph, and copybook names in parentheses for traceability. Items whose source was not fully extracted are explicitly marked [UNKNOWN] with the closure action required.

The document distinguishes two classes of non-functional expectations:
- **Current-Baseline NFRs** are enforced by existing code paths and are verifiable today.
- **Target-State NFRs** are contractual expectations for v1 GA whose enforcement hooks must be added during implementation; these are tagged explicitly.

### 1.5 In-Scope / Out-of-Scope Decisions
| Area | Decision | Rationale |
|---|---|---|
| Minecraft protocol 769 / 1.21.4 | IN SCOPE | Version fixed in `DD-VERSION`. [CONFIRMED] |
| Code generation from upstream data reports | IN SCOPE | `CodegenMain` is a first-class deliverable. [CONFIRMED] |
| Multi-choice shapeless recipes (> 1 choice/tag/array ingredient) | OUT OF SCOPE (v1) | Parser supports at most one choice/tag/array ingredient per recipe at build time. [CONFIRMED — `Parse-Recipe-Shapeless`] |
| Loot functions `apply_bonus`, `copy_components`, `copy_state`; entry type `minecraft:dynamic` | OUT OF SCOPE (v1) | Generator currently emits empty/no-op callbacks (TODO) for these paths. [CONFIRMED — `codegen/generators/blocks_loot_table`] |
| Online-mode authentication / Mojang session validation | OUT OF SCOPE (v1) | Offline UUID derivation in `Players-NameToUUID`; no authentication path observed. [CONFIRMED] |
| Internationalization of chat / death messages | OUT OF SCOPE (v1) | No locale layer observed. [INFERRED — absence] |
| Multithreaded tick execution | OUT OF SCOPE (v1) | EXTERNAL shared state in copybooks implies a single-threaded model. [INFERRED — `src/_copybooks/state`] |

### 1.6 Key Business Capabilities
1. Player lifecycle (connect, tick, damage/death, save, disconnect). [CONFIRMED]
2. World and chunk management with block updates, block entities, entity simulation, and persistence. [CONFIRMED]
3. Inventory and crafting, including shaped, shapeless, and complex recipes. [CONFIRMED]
4. Command subsystem: `/gamemode`, `/help`, `/kill`, `/save`, `/say`, `/stop`, `/time`, `/whitelist`. [CONFIRMED]
5. Chat broadcasting and console messaging. [CONFIRMED]
6. Code generation toolchain for registries, packets, items, and block loot tables. [CONFIRMED]
7. Four-level test framework (suite → unit → case → assertion). [CONFIRMED]

---

## 2. System Overview

### 2.1 Major Subsystems

| Subsystem | Path | Responsibility | Evidence |
|---|---|---|---|
| Runtime Server Core | `src/` | Player, world, block, block entity, entity, inventory, command, chat, utility logic | [CONFIRMED] |
| Protocol / Packets | `src/packets` | Packet encode/decode and handlers | [CONFIRMED — module exists] / Detailed packet contracts [UNKNOWN — TBD-02] |
| Parsers | `src/parsers` | Recipe parsers (shaped, shapeless, result) | [CONFIRMED] |
| Encoding Utilities | `src/encoding` | VarInt, hex, SHA-1, UUID, binary encode/decode | [CONFIRMED — module exists] / Full routine inventory [UNKNOWN — TBD-04] |
| Shared Copybooks | `src/_copybooks` | EXTERNAL state, callbacks, constants, structures | [CONFIRMED — directory listing] / Several copybook PIC/USAGE [UNKNOWN — TBD-03] |
| Code Generator | `codegen/` | Template-driven COBOL emission | [CONFIRMED] |
| Test Harness | `tests/` | Four-level test framework and suites | [CONFIRMED] |

### 2.2 Runtime Flow (High-Level)
The runtime tick loop is reconstructed from observed module boundaries; full orchestration is not directly extracted and is marked [INFERRED] below.

1. Startup initializes the player slot table (`Players-Init`), registries, and block/item/block-entity/entity callbacks. [INFERRED — derived from `Register*` call sites]
2. The server enters a tick loop that processes player ticks (`Players-Tick`), entity ticks, world events, and packet I/O. [INFERRED]
3. Commands are parsed and dispatched via callback pointer tables. [CONFIRMED — `RegisterCommand-*` and parser tree]
4. World, chunk, and player mutations are flushed on `/save`, periodic save (`Server-Save`), or disconnect. [CONFIRMED]
5. Shutdown is triggered by `/stop` invoking `Server-Stop`. [CONFIRMED]

### 2.3 Build-Time Flow (Code Generation)
`CodegenMain` requires three mandatory arguments: `DATADIR`, `OUTDIR`, `TPLDIR`. [CONFIRMED]

1. Validate and set directories (`Codegen-SetDataDirectory`, `Codegen-SetOutputDirectory`, `Codegen-SetTemplateDirectory`). [CONFIRMED]
2. Load registries (`CG-LoadRegistries` from `generated/reports/registries.json`). [CONFIRMED]
3. Execute generators in order: packets → registries → items → blocks loot tables. [CONFIRMED]

### 2.4 Client Lifecycle States
Declared as 78-level constants: `DISCONNECTED = −1`, `HANDSHAKE = 0`, `STATUS = 1`, `LOGIN = 2`, `CONFIGURATION = 3`, `PLAY = 4`. [CONFIRMED]

### 2.5 Glossary
| Term | Definition |
|---|---|
| Block type | Logical category registered in `minecraft:block` (e.g., `minecraft:stone`). |
| Block state ID | Numeric state identifier assigned to one specific property combination of a block type. |
| Block type ID | Numeric identifier of a block type (distinct from block state ID). |
| Section | 16×16×16 vertical slice of a chunk. |
| Chunk | 16×384×16 column addressed by (chunk_x, chunk_z). |
| Client | Network peer; holds a lifecycle state. |
| Player | Client in `PLAY` state bound to a player slot. |
| Block ID | Throughout this document, "block ID" always refers to **block state ID** unless explicitly qualified as "block type ID." |

---

## 3. Functional Requirements

Every requirement follows the format: Input → Processing → Output → Positive Acceptance → Negative Acceptance → Traceability → Verification. Identifiers are globally unique. Evidence tags reflect the strongest available source grounding.

### 3.1 Code Generation

#### FR-CG-001 — Mandatory CLI Arguments
- **Statement:** The system shall require three non-blank directory arguments (data, output, template) before any generation runs.
- **Input:** Three positional arguments on program invocation.
- **Processing:** Validate each argument is present and non-blank via `Codegen-SetDataDirectory`, `Codegen-SetOutputDirectory`, `Codegen-SetTemplateDirectory`.
- **Output:** On success, directories are bound. On failure, a usage message is written to standard error and the process exits with code 1.
- **Positive Acceptance:** All three directories provided and non-blank → generation proceeds.
- **Negative Acceptance:** Any missing/blank argument → `STOP RUN RETURNING 1` after usage message.
- **Traceability:** `codegen/CodegenMain.cob`. [CONFIRMED]
- **Verification:** CLI integration test (TC-CG-001) invoking with 0, 1, 2, 3 args and with blanks.

#### FR-CG-002 — Registry Loading
- **Statement:** The system shall parse `generated/reports/registries.json` and populate indexed lookup arrays keyed by `protocol_id + 1`.
- **Input:** JSON file read via `Codegen-ReadDataFile`.
- **Processing:** For each registry, record its name at `REGISTRY-NAME(protocol_id + 1)`; for each entry, record its name at `REGISTRY-ENTRY-NAME(registry_id + 1, entry_id + 1)`.
- **Output:** Populated `DD-REGISTRIES` arrays.
- **Positive Acceptance:** All registries and entries present and contiguous by `protocol_id`, loaded without assertion.
- **Negative Acceptance:** Missing `protocol_id`, non-contiguous indices, or JSON parse errors → assertion termination.
- **Traceability:** `codegen/data/CG-LoadRegistries.cob`. [CONFIRMED]
- **Verification:** Unit tests with malformed fixtures (missing id, gap in ids, non-object root).

#### FR-CG-003 — Template Pipeline
- **Statement:** The system shall load a template, evaluate `$var$` placeholders with optional transforms `indent=<n>` and `newline=after`, and iteratively optimize the output until its size is stable.
- **Input:** Template path; optional replacement callback `REPLACE-PTR`.
- **Processing:** `Codegen-TemplateLoad` → `Codegen-TemplateEval` → `Codegen-Optimize` (fixed-point on output length).
- **Output:** Optimized COBOL text appended via `Codegen-Start` / `Codegen-Append` / `Codegen-End`.
- **Positive Acceptance:** Known transforms applied; output produced; optimizer terminates.
- **Negative Acceptance:** Unknown transform → `ASSERT-FAILED` termination. [CONFIRMED] Behavior when a `$var$` placeholder has no binding via `REPLACE-PTR` is [UNKNOWN] and must be characterized and specified during implementation (see TBD-07).
- **Traceability:** `codegen/common/template.cob`. [CONFIRMED — transform path]
- **Verification:** Existing template tests plus a new case for unknown transforms; add a characterization test for unbound variables once behavior is confirmed.

#### FR-CG-004 — Packet Source Generation
- **Statement:** The system shall emit `packets.cob` from packet template definitions and loaded registries.
- **Processing:** `CG-Packets` enumerates packet descriptors and invokes the template pipeline.
- **Positive Acceptance:** Output file exists, compiles under target GnuCOBOL, and contains one entry per declared packet descriptor.
- **Negative Acceptance:** Missing registry entries referenced by packets → assertion termination.
- **Traceability:** `codegen/generators/packets/*`. [CONFIRMED]
- **Verification:** Build-time smoke compile plus golden-file comparison against the committed artifact.

#### FR-CG-005 — Registries Source Generation
- **Statement:** The system shall emit a COBOL registries source containing all registry and entry names in contiguous arrays.
- **Positive Acceptance:** Output size matches registry population; indices are 1-based in COBOL and zero-based `protocol_id` externally.
- **Traceability:** `codegen/generators/registries/*`. [CONFIRMED]
- **Verification:** Golden-file comparison; integration test loading emitted arrays.

#### FR-CG-006 — Items Source Generation
- **Statement:** The system shall emit an items source for each item with `minecraft:max_stack_size > 0`.
- **Negative Acceptance:** Any item with missing/zero `max_stack_size` → assertion termination.
- **Traceability:** `codegen/generators/items/CG-Items-Main.cob`. [CONFIRMED]
- **Verification:** Fixture item with `max_stack_size = 0` → build fails.

#### FR-CG-007 — Blocks Loot Table Source Generation
- **Statement:** The system shall emit block-loot-table callbacks from `generated/data/minecraft/loot_table/blocks/*.json`, subject to the validation rules defined in BR-030.
- **Current-State Behavior:** The generator asserts on malformed pool structure per BR-030. For unsupported features enumerated in BR-035 (e.g., loot functions `apply_bonus`, `copy_components`, `copy_state`; entry type `minecraft:dynamic`), the current implementation emits a no-op or TODO branch rather than a hard assertion. [CONFIRMED — TODO/CONTINUE paths observed]
- **Target-State Requirement (v1 GA):** The generator shall reject unsupported features with an explicit assertion and a descriptive diagnostic, replacing current TODO/CONTINUE paths. This closure is required before v1 GA (see R-H-003 and Section 9).
- **Positive Acceptance:** Supported loot tables produce emitted callbacks that compile and match golden fixtures.
- **Negative Acceptance (current):** Pools violating BR-030 cause assertion termination.
- **Negative Acceptance (target):** Unsupported features per BR-035 cause assertion termination.
- **Traceability:** `codegen/generators/blocks_loot_table/*`. [CONFIRMED — current behavior]
- **Verification:** Fixture JSON exercises each BR-030 path today; BR-035 fixtures will be added alongside the target-state change.

---

### 3.2 Player Lifecycle

#### FR-PL-001 — Player Connect
- **Statement:** The system shall allocate the first free player slot on connect and initialize defaults from persisted data when available.
- **Input:** `LK-CLIENT-ID`, `LK-UUID` (16 bytes), `LK-NAME` (16 chars).
- **Processing:** Locate the first slot where `PLAYER-CLIENT = 0`; initialize defaults; determine spawn via `World-FindSpawnLocation`; attempt best-effort load via `Players-LoadPlayer`; bind client, UUID, and name.
- **Output:** `LK-PLAYER-ID` (0 if all slots full).
- **Positive Acceptance:** Free slot found → player bound, non-zero ID returned.
- **Negative Acceptance:** No free slot → returns 0; load failure leaves defaults in place (connect still succeeds).
- **Traceability:** `src/players/Players-Connect.cob`. [CONFIRMED]
- **Verification:** TC-PL-001 (slot full), TC-PL-002 (corrupt playerdata file).

#### FR-PL-002 — Player Disconnect
- **Statement:** The system shall close any open window, save the player, and release the slot on disconnect.
- **Processing:** Invoke the window-close callback when present; `Players-SavePlayer`; set `PLAYER-CLIENT = 0`.
- **Positive Acceptance:** Slot is reusable immediately after disconnect.
- **Negative Acceptance:** A save error is logged but does not block slot release.
- **Traceability:** `src/players/Players-Disconnect.cob`. [CONFIRMED]
- **Verification:** Inject write failure and verify the slot becomes free.

#### FR-PL-003 — Save Player
- **Statement:** The system shall persist player state as gzip-compressed NBT at `<level>/playerdata/<uuid>.dat`.
- **Processing:** Build the NBT document (core stats, inventory excluding the crafting output slot, abilities); `GzipCompress`; ensure directory exists via `CBL_CREATE_DIR`; write via `Files-WriteAll`.
- **Positive Acceptance:** File written; returns `LK-FAILURE = 0`.
- **Negative Acceptance:** Compression or I/O failure → `LK-FAILURE = 1`.
- **Slot Mapping:** Inventory slot 1 (crafting output) is excluded; remaining slots are remapped between internal and NBT conventions; item IDs serialize as registry strings.
- **Traceability:** `src/players/Players-SavePlayer.cob`. [CONFIRMED]
- **Verification:** TC-PL-003 byte-level NBT round-trip; TC-PL-004 induced compression failure.

#### FR-PL-004 — Load Player
- **Statement:** The system shall load a player file when present, transparently decompressing gzip payloads and skipping unknown tags.
- **Processing:** Read file; if the magic bytes `1F 8B` are present, `GzipDecompress`; parse NBT root compound; resolve item registry strings to numeric IDs.
- **Positive Acceptance:** Known tags are mapped; unknown tags are ignored.
- **Negative Acceptance:** Absent gzip magic → treated as uncompressed (current behavior); corrupt NBT after decode → returns failure and caller retains defaults. Additional corruption-handling policy is tracked under R-M-008.
- **Traceability:** `src/players/Players-LoadPlayer.cob`. [CONFIRMED]
- **Verification:** Fixtures for compressed, uncompressed, truncated, and unknown-tag files.

#### FR-PL-005 — Player Tick
- **Statement:** Each tick, the system shall update time, decrement the hurt timer, apply void damage below Y = −128, regenerate 1 HP per 20 ticks (capped at 20), and emit `SetHealth` for each client in `CLIENT-STATE-PLAY`.
- **Positive Acceptance:** Dead players are excluded from regeneration; only `PLAY` clients are ticked.
- **Traceability:** `src/players/Players-Tick.cob`. [CONFIRMED]
- **Verification:** TC-PL-005 regen cap; TC-PL-006 void threshold boundary (Y = −128 and Y = −129); TC-PL-007 dead-player no-regen.

#### FR-PL-006 — Movement and Fall Damage
- **Statement:** The system shall accumulate fall distance and apply damage equal to `max(0, fall_distance − 3.0)` when the player lands, suppressing damage if `world_time < 20` or while flying.
- **Positive Acceptance:** Thresholds enforced; flying flag disables accumulation.
- **Negative Acceptance:** Landing with fall distance ≤ 3.0 → no damage.
- **Traceability:** `src/players/Players-HandleMove.cob`. [CONFIRMED]
- **Verification:** Boundary tests at fall_distance ∈ {2.99, 3.00, 3.01}; flying-toggle tests.

#### FR-PL-007 — Damage Application
- **Statement:** The system shall apply HP reduction per the immunity matrix below, set `hurt_time = 10`, play the appropriate sound, and on death emit the death event and broadcast the death message.
- **Immunity Matrix:**
  | Condition | `generic_kill` | `out_of_world` | Other |
  |---|---|---|---|
  | Dead | Immune | Immune | Immune |
  | Creative | NOT immune | NOT immune | Immune |
  | `hurt_time > 0` | NOT immune | Immune | Immune |
  | Default | NOT immune | NOT immune | NOT immune |
- **Traceability:** `src/players/Players-Damage.cob`. [CONFIRMED]
- **Verification:** Parameterized matrix test over all damage types × states.

#### FR-PL-008 — Player Lifecycle State Machine
- **Statement:** The system shall enforce the following player lifecycle states and transitions. All other transitions are invalid.

```
[Disconnected] --connect--> [Loading] --loaded--> [Playing]
                                     --load_fail_default--> [Playing]
[Playing] --damage_lethal--> [Dead]
[Playing] --disconnect--> [Disconnected]
[Dead] --disconnect--> [Disconnected]
[Dead] --respawn--> [Playing]  [INFERRED — respawn path not confirmed in extracted source]
```

- **Guards:** Entry into `Playing` requires bound `CLIENT-ID`, `UUID`, and `NAME`. Entry into `Dead` requires `health ≤ 0`. Regeneration and movement handlers are no-ops while `Dead`.
- **Traceability:** Synthesized from `Players-Connect`, `Players-LoadPlayer`, `Players-Damage`, `Players-Tick`. [INFERRED] The `respawn` transition source is [UNKNOWN — TBD-08].
- **Verification:** State-transition coverage test enumerating all confirmed (state, event) pairs; the `respawn` case remains pending TBD-08 closure.

---

### 3.3 World and Blocks

#### FR-WB-001 — Vertical World Bounds
- **Statement:** The system shall accept world Y coordinates only in the inclusive range [−64, 319].
- **Output:** `LK-RESULT = 0` if within bounds; `1` otherwise.
- **Traceability:** `src/world/World-CheckBounds.cob`. [CONFIRMED]
- **Verification:** Boundary tests at Y ∈ {−65, −64, 319, 320}.

#### FR-WB-002 — Read Block State
- **Statement:** The system shall return the block state ID at a world coordinate, or 0 if the containing chunk is not loaded.
- **Processing:** Floor-divide coordinates by 16 to find chunk and section; compute the block index.
- **Traceability:** `src/world/World-GetBlock.cob`. [CONFIRMED]
- **Verification:** Chunk-absent and chunk-present tests.

#### FR-WB-003 — Set Block State
- **Statement:** The system shall update a block state, maintain section non-air counters, remove incompatible block entities on type change, mark the chunk dirty, and broadcast updates to `PLAY` clients. Transitions to air shall emit `WORLD-EVENT-BLOCK-BREAK (2001)`.
- **No-op Conditions:** Chunk absent; new state equals current state.
- **Traceability:** `src/world/World-SetBlock.cob`. [CONFIRMED]
- **Verification:** Unit tests for no-op, dirty-flag assertion, and broadcast invocation.

#### FR-WB-004 — Save Chunk
- **Statement:** The system shall persist dirty chunks to region and entity files, writing only non-air sections, and using palette-packed long arrays when palette size > 1.
- **Processing:** Build block and biome palettes; serialize block entities and runtime entities via registered callbacks; write via `Region-WriteChunkData`; clear dirty flags.
- **Traceability:** `src/world/World-SaveChunk.cob`. [CONFIRMED]
- **Verification:** Round-trip fixture; assertion that non-dirty chunks are not written.

#### FR-WB-005 — Block Behavior Callbacks
- **Statement:** The system shall register per-block-type behavior callbacks; `RegisterBlock-Generic` provides defaults while specialized modules override.
- **Solidity Rules:**
  | Block | Face Solidity |
  |---|---|
  | air, water, lava, bed, door, torch, tall_grass | Non-solid (all faces) |
  | slab `double` | Solid all faces |
  | slab `bottom` | Solid down only |
  | slab `top` | Solid up only |
  | trapdoor open | Non-solid |
  | trapdoor closed `top` | Solid up only |
  | trapdoor closed `bottom` | Solid down only |
  | generic | Solid all faces |
- **Paired-Half Rules:** Bed and door destroy removes both halves; door/trapdoor open-toggle mirrors to the counterpart half. Torch destroy remaps wall-torch variants to standing-torch item names before drop.
- **Traceability:** `src/blocks/RegisterBlock-*.cob`. [CONFIRMED]
- **Verification:** Matrix tests per block type and face.

#### FR-WB-006 — Spawn Chunk Protection
- **Statement:** The system shall retain the 3×3 chunk region around the configured spawn as resident and prevent it from being unloaded during runtime.
- **Status:** [INFERRED — specific implementation paragraph not extracted; tracked in TBD-01.] Approval of this requirement is blocked until TBD-01 is closed.
- **Traceability:** `src/world/*`. [INFERRED]
- **Verification:** Integration test issuing chunk-unload requests while spawn set remains loaded. Requires TBD-01 closure.

---

### 3.4 Inventory and Crafting

#### FR-IC-001 — Store Item
- **Statement:** The system shall place a candidate stack by first merging into compatible non-full stacks (hotbar slots 37–45, main inventory slots 10–36), then by filling the first empty slot.
- **Traceability:** `src/inventory/Inventory-StoreItem.cob`. [CONFIRMED]
- **Verification:** Tests for partial merge, overflow remainder, and empty inventory.

#### FR-IC-002 — Compare Items
- **Statement:** The system shall treat two item stacks as compatible only when both are non-empty, share an item ID, and have identical NBT length and bytes.
- **Traceability:** `src/inventory/Inventory-CompareItems.cob`. [CONFIRMED]
- **Verification:** Same-ID differing-NBT negative test.

#### FR-IC-003 — Update Crafting Output
- **Statement:** The system shall evaluate crafting input (2×2 or 3×3, mapped to internal 3×3) and populate the output slot with `result.id`, `result.count` (default 1), and empty-NBT marker `X"0000"` when a recipe matches.
- **Algorithms:** Shapeless (sort multiset descending, compare); shaped (compact to top-left, then exact or per-slot options). Mismatch clears the output.
- **Traceability:** `src/inventory/Inventory-UpdateCraftingOutput.cob`. [CONFIRMED]
- **Verification:** Matrix over shapeless, shaped exact, shaped complex, mirrored asymmetrical, and no-match.

#### FR-IC-004 — Pick Item
- **Statement:** The system shall prefer an existing hotbar match; otherwise swap from main inventory. In creative mode, it shall materialize the item in the held slot if empty.
- **Traceability:** `src/inventory/Inventory-PickItem.cob`. [CONFIRMED]
- **Verification:** Survival vs. creative tests.

#### FR-IC-005 — Windows (Player, Crafting Table)
- **Statement:** The system shall provide `sync`, `close`, `set-slot`, and `drop` callbacks per window. Close shall return or drop transient mouse and crafting-input items. Set-slot on a crafting input shall require sync and recompute the output. Drop on output shall consume one unit from each non-empty input.
- **Traceability:** `src/inventory/RegisterWindow-Player.cob`, `RegisterWindow-Crafting.cob`. [CONFIRMED]
- **Verification:** Per-callback tests for each window with exhaustive slot-class coverage.

---

### 3.5 Commands

All commands set `LK-PRINT-USAGE = 1` on invalid syntax and translate I/O failures to the message "Input/output error." "Invalid syntax" means argument-count or literal/argument-type mismatches enforced by the parser tree; richer input validation (encoding, length) is addressed in FR-CMD-009 as a target-state requirement.

#### FR-CMD-001 — `/gamemode <mode> [player]`
- **Statement:** The system shall set the target player's mode (survival, creative, adventure, spectator), adjust the `flying` flag, and send `GameEvent` plus `PlayerAbilities`. Console invocations must include an explicit player.
- **Traceability:** `src/commands/RegisterCommand-Gamemode.cob`. [CONFIRMED]
- **Verification:** Per-mode and console-without-target tests.

#### FR-CMD-002 — `/help`
- **Statement:** The system shall iterate `COMMAND-COUNT` entries and print each `COMMAND-HELP` string.
- **Traceability:** `src/commands/RegisterCommand-Help.cob`. [CONFIRMED]
- **Verification:** Snapshot of emitted output for a known command set.

#### FR-CMD-003 — `/kill [player]`
- **Statement:** The system shall apply a near-`FLOAT-SHORT`-max damage value with type `minecraft:generic_kill`. Console invocations must include an explicit player.
- **Traceability:** `src/commands/RegisterCommand-Kill.cob`. [CONFIRMED]
- **Verification:** Immunity-matrix interaction test; console-without-target test.

#### FR-CMD-004 — `/save`
- **Statement:** The system shall emit a start message, call `Server-Save`, and emit a completion message.
- **Traceability:** `src/commands/RegisterCommand-Save.cob`. [CONFIRMED]

#### FR-CMD-005 — `/say <message>`
- **Statement:** The system shall broadcast a greedy message prefixed with `[Server]` for console or `[<Name>]` for players.
- **Empty-Message Handling:** [UNKNOWN — TBD-09] The target-state requirement is to reject empty or whitespace-only messages with `LK-PRINT-USAGE = 1`. Current behavior is not characterized.
- **Traceability:** `src/commands/RegisterCommand-Say.cob`. [CONFIRMED — greedy broadcast path]
- **Verification:** Empty message, unicode, trailing whitespace, 1024-byte maximum. Empty-message verification depends on TBD-09 closure.

#### FR-CMD-006 — `/stop`
- **Statement:** The system shall invoke `Server-Stop` and exit the tick loop.
- **Traceability:** `src/commands/RegisterCommand-Stop.cob`. [CONFIRMED]

#### FR-CMD-007 — `/time set <alias|ticks>`
- **Statement:** The system shall map `day=1000`, `noon=6000`, `night=13000`, `midnight=18000`; otherwise parse a non-negative numeric tick value via `NUMVAL`.
- **Traceability:** `src/commands/RegisterCommand-Time.cob`. [CONFIRMED]
- **Verification:** Aliases, negative numbers, non-numeric, overflow.

#### FR-CMD-008 — `/whitelist (reload|on|off|list|add|remove) [player]`
- **Statement:** The system shall manage the whitelist; `list` dynamically allocates a buffer beyond 128 bytes and frees it; `add`/`remove` resolve UUID from name via `Players-NameToUUID`.
- **Traceability:** `src/commands/RegisterCommand-Whitelist.cob`. [CONFIRMED]
- **Verification:** List > 128 bytes; add duplicate; remove missing; reload without file.

#### FR-CMD-009 — Command Input Hygiene (Target-State)
- **Statement (Target):** The system shall reject commands whose argument count does not match the parser tree (confirmed behavior); additionally, it shall reject inputs exceeding declared buffer lengths or containing invalid UTF-8. Rejection uses `LK-PRINT-USAGE = 1`.
- **Current-State Baseline:** The parser tree enforces argument-count/literal-type structure only. [CONFIRMED] Explicit length-overflow and UTF-8 validation logic is [UNKNOWN] in current source and must be added.
- **Traceability:** `src/commands/*` parser tree. [CONFIRMED — argument-count path] / [UNKNOWN — UTF-8/length path]
- **Verification:** Structural rejection today; fuzz tests for oversized payloads and malformed unicode after implementation.

---

### 3.6 Entities

#### FR-EN-001 — Generic Entity Registration
- **Statement:** The system shall register base `serialize`, `deserialize`, and `tick` callbacks for every entry of `minecraft:entity_type`.
- **Traceability:** `src/entities/RegisterEntity-Generic.cob`. [CONFIRMED]

#### FR-EN-002 — Base Entity Serialization
- **Statement:** The system shall serialize UUID, `Pos` (3 doubles), `Rotation` (2 floats), `Motion` (3 doubles), `OnGround`, and `NoGravity`, and shall skip unknown tags on deserialization.
- **Traceability:** `src/entities/EntityBase-Serialize.cob`, `EntityBase-Deserialize.cob`. [CONFIRMED]

#### FR-EN-003 — Item Entity Behavior
- **Statement:** The system shall tick item entities according to the following physics and lifecycle rules:
  - Expire when `age > 6000` ticks.
  - Apply motion drag 0.98 per tick and gravity −0.04 on Y.
  - Zero velocity upon collision with a solid (non-replaceable) block.
  - Decrement pickup delay to a minimum of 0; while delay is 0, perform an expanded AABB check against players and call `Inventory-StoreItem`.
  - On any pickup (including partial), broadcast `SendPacket-TakeItemEntity`; remove the entity when remaining count < 1.
- **Traceability:** `src/entities/RegisterEntity-Item.cob`. [CONFIRMED]
- **Verification:** Lifetime boundary, drag/gravity numerical tests, partial pickup, delay boundary.

---

### 3.7 Chat and Broadcast

#### FR-CH-001 — Send Chat Message
- **Statement:** The system shall treat `Client ID = 0` as console output (no packet sent); the default text color shall be white; the default byte count shall equal `STORED-CHAR-LENGTH`.
- **Traceability:** `src/util/chat.cob` → `SendChatMessage`. [CONFIRMED]

#### FR-CH-002 — Broadcast Chat Message
- **Statement:** The system shall broadcast only to clients in `CLIENT-STATE-PLAY`, optionally excluding a specified client, and shall always log the message to the console.
- **Traceability:** `BroadcastChatMessage`, `BroadcastChatMessageExcept`. [CONFIRMED]

---

### 3.8 Server Properties

#### FR-SP-001 — Defaults on Empty Input
- **Statement:** The system shall initialize defaults: `port = 25565`, `level-name = "world"`, `whitelist = false`, `motd = "CobolCraft"`, `max-players = 10`, `max-clients = 10`.
- **Traceability:** `ServerProperties-Deserialize` and accompanying tests. [CONFIRMED]

#### FR-SP-002 — Validation
- **Statement:** The system shall reject empty `level-name`, non-numeric `server-port`, and `max-players = 0`. Empty `motd` is permitted (`SP-MOTD` all spaces).
- **Traceability:** `ServerProperties-Deserialize` and accompanying tests. [CONFIRMED]

#### FR-SP-003 — Canonical Serialization
- **Statement:** The system shall emit a comment header followed by ordered keys, byte-identical to the test expectation.
- **Traceability:** `ServerProperties-Serialize`. [CONFIRMED]

---

### 3.9 Region File Naming

#### FR-RG-001 — Region and Entity File Path
- **Statement:** The system shall produce file paths of the form `<level-name>/(region|entities)/r.<x>.<z>.mca`, supporting negative coordinates.
- **Traceability:** `src/world/Region-RegionFileName.cob`. [CONFIRMED]

---

### 3.10 Test Framework

#### FR-TS-001 — Hierarchy Enforcement
- **Statement:** The system shall enforce the Suite → Unit → Case → Assertion hierarchy; each level requires at least one child of the next level or the run terminates with a non-zero exit code.
- **Traceability:** `tests/test.cob`. [CONFIRMED]

#### FR-TS-002 — Aggregation and Exit
- **Statement:** `TestMain` shall aggregate counts, exit 0 only when all assertions pass and at least one test has run, and otherwise exit non-zero.
- **Traceability:** `tests/TestMain.cob`. [CONFIRMED]

#### FR-TS-003 — Failure Capacity
- **Statement:** The runner shall store up to 100 failure records in `FAILED-TESTS`; additional failures shall be counted but not retained.
- **Traceability:** `tests/TestMain.cob`. [CONFIRMED]

---

## 4. Data Model

### 4.1 COBOL → Modern Type Mapping

| COBOL Declaration | Modern Type | Notes |
|---|---|---|
| `PIC X(n)` | fixed-length string(n) | Space-padded |
| `PIC X ANY LENGTH` | variable string | Linkage only |
| `BINARY-CHAR [UNSIGNED]` | int8 / uint8 | |
| `BINARY-SHORT [UNSIGNED]` | int16 / uint16 | |
| `BINARY-LONG [UNSIGNED]` | int32 / uint32 | |
| `BINARY-LONG-LONG` | int64 | |
| `FLOAT-SHORT` | float32 | |
| `FLOAT-LONG` | float64 | |
| `POINTER` / `PROGRAM-POINTER` | pointer / function pointer | |
| `OCCURS n` | fixed array[n] | |
| `OCCURS 0 TO m DEPENDING ON x` | dynamic array (bounded) | |
| 78-level constant | compile-time constant | |

### 4.2 Entities

#### 4.2.1 Player (`DD-PLAYERS`)
| Attribute | Modern Type | COBOL Source | Key/Notes |
|---|---|---|---|
| player_id | int32 | Slot index | Primary key within table |
| client_id | uint32 | `PLAYER-CLIENT` | 0 = free |
| uuid | byte[16] | `PLAYER-UUID` | Identity |
| name | string(16) | `PLAYER-NAME` | Display name |
| gamemode | uint8 | `PLAYER-GAMEMODE` | 0..3 |
| flying | uint8 | `PLAYER-FLYING` | Boolean |
| position | {x, y, z: float64} | `PLAYER-POSITION-*` | — |
| rotation | {yaw, pitch: float32} | `PLAYER-ROTATION-*` | — |
| on_ground | uint8 | `PLAYER-ON-GROUND` | Boolean |
| fall_distance | float32 | `PLAYER-FALL-DISTANCE` | — |
| hurt_time | int16 | `PLAYER-HURT-TIME` | Immunity timer |
| health | float32 | `PLAYER-HEALTH` | HP |
| food | int32 | `PLAYER-FOOD` | Exact PIC/USAGE [UNKNOWN — TBD-03] |
| experience | int32 | `PLAYER-EXPERIENCE` | Exact PIC/USAGE [UNKNOWN — TBD-03] |
| selected_slot | int32 | `PLAYER-SELECTED-SLOT` | Hotbar selection |
| inventory[46] | InventorySlot[] | `PLAYER-INVENTORY` | Slot 1 excluded from save |
| abilities.flying | uint8 | `PLAYER-ABILITIES-FLYING` | — |
| update_sign_position | {x, y, z: int32} | `PLAYER-UPDATE-SIGN-*` | Sign editor target |

#### 4.2.2 Inventory Slot (`DD-INVENTORY-SLOT`)
| Attribute | Modern Type | Notes |
|---|---|---|
| id | uint32 | 0 = empty |
| count | uint32 | 0 = empty |
| nbt_length | uint32 | bytes |
| nbt_data | byte[nbt_length] | Raw components/NBT |

#### 4.2.3 Block State Description (`DD-BLOCK-STATE`)
| Attribute | Modern Type | Notes |
|---|---|---|
| name | string | Block type identifier |
| property_count | int32 | |
| properties[i].name | string | |
| properties[i].value | string | |
| description | string | Serialized descriptor `DESCRIPTION` |

#### 4.2.4 Chunk (`DD-CHUNK-REF`)
| Attribute | Modern Type | Notes |
|---|---|---|
| chunk_x | int32 | |
| chunk_z | int32 | |
| sections[] | Section | Up to 24 sections; palette + packed long array |
| biomes_palette | Palette | |
| dirty_flags | {chunk, entities: uint8} | |
| block_entities | map<pos, BlockEntity> | |
| entities_head | pointer | Linked-list head |

Exact PIC/USAGE [UNKNOWN — TBD-03].

#### 4.2.5 Entity (`DD-ENTITY`)
| Attribute | Modern Type | Notes |
|---|---|---|
| id | int32 | Server-assigned |
| uuid | byte[16] | |
| type | int32 | Registry ID into `minecraft:entity_type` |
| position | {x, y, z: float64} | |
| motion | {x, y, z: float64} | |
| rotation | {yaw, pitch: float32} | |
| on_ground | uint8 | |
| no_gravity | uint8 | |
| metadata | compound | Includes `item_slot` for item entities |

#### 4.2.6 Sign Block Entity (`DD-BLOCK-ENTITY-SIGN`)
| Attribute | Modern Type | Notes |
|---|---|---|
| is_waxed | uint8 | |
| front_text.has_glowing_text | uint8 | |
| front_text.color | string | Default "black" |
| front_text.messages[4] | string | Default `""` JSON (length 2) |
| back_text.* | same as front_text | |

#### 4.2.7 Registry (`DD-REGISTRIES`)
| Attribute | Modern Type | Notes |
|---|---|---|
| registry_count | int32 | |
| registries[i].name | string | Indexed by `protocol_id + 1` |
| registries[i].entry_count | int32 | |
| registries[i].entries[j].name | string | Indexed by `entry_id + 1` |

#### 4.2.8 Recipe (`DD-RECIPES`)
| Attribute | Modern Type | Notes |
|---|---|---|
| type | enum{shapeless, shaped, complex} | |
| shapeless.ids[] | int32 | Sorted descending multiset |
| shaped.grid[3][3] | int32 | Fixed 3×3 |
| complex.slot_options[9][] | int32 | Per-slot option list |
| result.id | int32 | |
| result.count | int32 | Default 1 |

#### 4.2.9 Server Properties (`DD-SERVER-PROPERTIES`)
| Attribute | Modern Type | Default | Validation |
|---|---|---|---|
| port | int32 | 25565 | Numeric, > 0 |
| level_name | string | "world" | Non-empty |
| whitelist_enable | uint8 | 0 | Boolean |
| motd | string | "CobolCraft" | May be empty |
| max_players | int32 | 10 | > 0 |
| max_clients | int32 | 10 | > 0 |

Exact PIC/USAGE [UNKNOWN — TBD-03].

#### 4.2.10 Whitelist (`DD-WHITELIST`)
| Attribute | Modern Type | Notes |
|---|---|---|
| entries[].uuid | byte[16] | Identity |
| entries[].name | string(16) | Display name |

Persisted on-disk format [UNKNOWN — TBD-06].

### 4.3 Relationships and Cardinality

| Parent | Child | Cardinality | Key |
|---|---|---|---|
| Player | InventorySlot | 1 : 46 | slot_index |
| Player | UUID | 1 : 1 | uuid (identity) |
| Chunk | Section | 1 : N (up to 24) | y_index |
| Chunk | BlockEntity | 1 : N | (x, y, z) |
| Chunk | Entity | 1 : N (linked list) | entity.id |
| World | Chunk | 1 : N | (chunk_x, chunk_z) |
| Registry | RegistryEntry | 1 : N | entry.protocol_id |
| Recipe | InputSet/Grid | 1 : 1 | — |
| Recipe | Result | 1 : 1 | — |
| ServerProperties | Whitelist | 1 : 1 (toggle) | — |

---

## 5. Process Flows

All flows cite the operations named in Section 3.

### 5.1 Player Connect
```
Client Login
 → Players-Connect(client_id, uuid, name)
     ├─ FR-PL-001: locate free slot (PLAYER-CLIENT = 0) else return 0
     ├─ initialize defaults + World-FindSpawnLocation
     ├─ Players-LoadPlayer(uuid)    [best-effort; FR-PL-004]
     └─ bind client_id, uuid, name
 → state = Playing  (FR-PL-008)
```

### 5.2 Tick Loop
```
Per tick:
 Players-Tick  (FR-PL-005)
   └─ for each CLIENT-STATE-PLAY client:
        time++; hurt_time--; void check (Y < −128); regen (every 20 ticks)
 Entity ticks  (FR-EN-003, et al.)
 Packet I/O and queued commands  (§7.3 — packet internals [UNKNOWN — TBD-02])
```

### 5.3 Block Break
```
Player input → RegisterBlock-*::Callback-Destroy
 → World-SetBlock(air)                 (FR-WB-003)
 → if gamemode ∈ {survival, adventure}: World-DropItem-FromBlock
 → World-SetBlock broadcasts BlockUpdate + WorldEvent 2001 to PLAY clients
 → if block entity present and type changed: remove block entity
```

### 5.4 Crafting Update
```
Slot change in crafting grid
 → Inventory-UpdateCraftingOutput  (FR-IC-003)
     ├─ MatchShapelessRecipes (sort ids desc)
     ├─ else MatchShapedRecipes (compact; exact or complex)
     └─ set output or clear
```

### 5.5 Command Execution
```
Console/client input
 → Command parser tree (literal/argument nodes)
 → Callback-Execute
     ├─ validate parts count (FR-CMD-009 baseline)
     ├─ resolve targets (self/player)
     ├─ perform action
     └─ feedback via SendChatMessage or BroadcastChatMessage
     (invalid syntax → LK-PRINT-USAGE = 1)
```

### 5.6 Save / Persistence
```
/save → Server-Save
 ├─ Players-Save: per connected player → Players-SavePlayer
 │      (NBT encode → GzipCompress → Files-WriteAll)   (FR-PL-003)
 └─ World-SaveChunk for dirty chunks → Region-WriteChunkData
     (region + entities files; FR-WB-004)
```

### 5.7 Code Generation
```
codegen DATADIR OUTDIR TPLDIR
 ├─ validate directories (FR-CG-001; failure → exit 1)
 ├─ CG-LoadRegistries (FR-CG-002)
 └─ CG-Packets → CG-Registries → CG-Items → CG-BlocksLootTable
     Each: TemplateLoad → Codegen-Start → TemplateEval (→ Optimize) → Append → End
```

### 5.8 Test Run
```
TestMain  (FR-TS-001/002)
 Suites: CPP, Strings, UUID, Decode, Encode, NbtEncode, NbtDecode,
         JsonParse, JsonEncode, Region, ServerProperties
 TestSuitePostValidate
 FAILED-TESTS capped at 100  (FR-TS-003)
 Exit 0 iff all passed AND tests executed
```

---

## 6. Business Rules

Every rule includes type, verification method, and source traceability to a concrete program file. Verification codes: `U` = unit, `I` = integration, `G` = golden-file, `F` = fuzz. A rule marked **Target** is contractual for v1 GA but not enforced by current source.

| ID | Rule | Type | Source (Program) | Evidence | Verification |
|---|---|---|---|---|---|
| BR-001 | Codegen requires all three directories; missing/blank → usage + RC=1. | Validation | `codegen/CodegenMain.cob` | [CONFIRMED] | U (TC-CG-001) |
| BR-002 | Registry and entry names must be contiguous by `protocol_id`. | Integrity | `codegen/data/CG-LoadRegistries.cob` | [CONFIRMED] | U (TC-CG-002) |
| BR-003 | Player files are gzip-compressed NBT at `<level>/playerdata/<uuid>.dat`. | Persistence | `src/players/Players-SavePlayer.cob` | [CONFIRMED] | I (TC-PL-003) |
| BR-004 | Player load transparently decompresses gzip (magic `1F 8B`) and skips unknown tags. | Robustness | `src/players/Players-LoadPlayer.cob` | [CONFIRMED] | U (TC-PL-004) |
| BR-005 | Vertical world bounds are inclusive [−64, 319]. | Validation | `src/world/World-CheckBounds.cob` | [CONFIRMED] | U (TC-WB-001) |
| BR-006 | Setting a new block type removes a stale block entity at that position. | Integrity | `src/world/World-SetBlock.cob` | [CONFIRMED] | U (TC-WB-003) |
| BR-007 | Item compatibility requires equal ID, equal NBT length, and byte-identical NBT. | Equality | `src/inventory/Inventory-CompareItems.cob` | [CONFIRMED] | U (TC-IC-002) |
| BR-008 | Crafting supports shapeless, shaped (normalized), and complex per-slot options. | Behavior | `src/inventory/Inventory-UpdateCraftingOutput.cob` | [CONFIRMED] | U/I (TC-IC-003) |
| BR-009 | `/time set` aliases: day=1000, noon=6000, night=13000, midnight=18000; otherwise `NUMVAL`. | Parsing | `src/commands/RegisterCommand-Time.cob` | [CONFIRMED] | U (TC-CMD-007) |
| BR-010 | `/whitelist list` dynamically allocates a buffer > 128 bytes and frees it. | Resource | `src/commands/RegisterCommand-Whitelist.cob` | [CONFIRMED] | U (TC-CMD-008) |
| BR-011 | Item entity expires at age > 6000 ticks; pickup only after delay = 0; partial consume allowed. | Lifecycle | `src/entities/RegisterEntity-Item.cob` | [CONFIRMED] | U (TC-EN-003) |
| BR-012 | Test hierarchy: suite → unit → case → assertion; violations terminate run. | Framework | `tests/test.cob` | [CONFIRMED] | Self-test |
| BR-013 | Chat `Client ID = 0` writes to console only (no packet emitted). | Behavior | `src/util/chat.cob` | [CONFIRMED] | U (TC-CH-001) |
| BR-014 | Broadcasts target only clients in `CLIENT-STATE-PLAY`. | Behavior | `src/util/chat.cob` | [CONFIRMED] | U (TC-CH-002) |
| BR-015 | Void damage applies below Y = −128. | Gameplay | `src/players/Players-Tick.cob` | [CONFIRMED] | U (TC-PL-006) |
| BR-016 | Regeneration: +1 HP every 20 ticks, capped at 20. | Gameplay | `src/players/Players-Tick.cob` | [CONFIRMED] | U (TC-PL-005) |
| BR-017 | Fall damage = `max(0, fall_distance − 3.0)`; ignored if `world_time < 20` or while flying. | Gameplay | `src/players/Players-HandleMove.cob` | [CONFIRMED] | U (TC-PL-006a) |
| BR-018 | Damage immunity per the matrix in FR-PL-007. | Gameplay | `src/players/Players-Damage.cob` | [CONFIRMED] | U (TC-PL-007) |
| BR-019 | `/kill` applies near-max-float damage typed `minecraft:generic_kill`. | Gameplay | `src/commands/RegisterCommand-Kill.cob` | [CONFIRMED] | U (TC-CMD-003) |
| BR-020 | Server property defaults: port=25565, level=world, whitelist=false, motd=CobolCraft, max_players=max_clients=10. | Config | `src/*/ServerProperties-*.cob` | [CONFIRMED] | U (TC-SP-001) |
| BR-021 | Reject empty `level-name`; accept empty `motd`; reject non-numeric port; reject `max-players = 0`. | Validation | `src/*/ServerProperties-Deserialize.cob` | [CONFIRMED] | U (TC-SP-002) |
| BR-022 | Region/entity file path is `<level>/(region\|entities)/r.<x>.<z>.mca` and supports negative coordinates. | Persistence | `src/world/Region-RegionFileName.cob` | [CONFIRMED] | U (TC-RG-001) |
| BR-023 | Block face solidity per FR-WB-005 matrix. | Behavior | `src/blocks/RegisterBlock-*.cob` | [CONFIRMED] | U matrix (TC-WB-005) |
| BR-024 | Bed/door destroy removes both halves; door/trapdoor open-toggle mirrors to counterpart half. | Integrity | `src/blocks/RegisterBlock-Bed.cob`, `-Door.cob`, `-Trapdoor.cob` | [CONFIRMED] | U (TC-WB-005a) |
| BR-025 | Dropping the crafting output consumes one unit from each non-empty input and recomputes. | Behavior | `src/inventory/RegisterWindow-Crafting.cob` | [CONFIRMED] | U (TC-IC-005) |
| BR-026 | Only dirty chunks/entities are persisted; only non-air sections serialized. | Optimization | `src/world/World-SaveChunk.cob` | [CONFIRMED] | I (TC-WB-004) |
| BR-027 | VarInt decode supports at most 5 bytes (32-bit). | Protocol | `src/encoding/Decode-VarInt.cob` | [CONFIRMED] | U (TC-EC-001) |
| BR-028 | Shapeless parser accepts at most one choice/tag/array ingredient per recipe at build time. | Limitation | `src/parsers/Parse-Recipe-Shapeless.cob` | [CONFIRMED] | U negative (TC-PR-001) |
| BR-029 | Shaped recipes with > 1 multi-choice slots are stored as complex; asymmetrical patterns are mirrored. | Behavior | `src/parsers/Parse-Recipe-Shaped.cob` | [CONFIRMED] | U (TC-PR-002) |
| BR-030 | Loot pool must have `rolls = 1.0`, `bonus_rolls = 0.0`, and exactly one entry. | Validation | `codegen/generators/blocks_loot_table/*` | [CONFIRMED] | U negative (TC-CG-007) |
| BR-031 | Item registry requires `minecraft:max_stack_size > 0`. | Validation | `codegen/generators/items/CG-Items-Main.cob` | [CONFIRMED] | U negative (TC-CG-006) |
| BR-032 | Spawn chunks (3×3 around spawn) are protected from unload during runtime. | Runtime | `src/world/*` (paragraph [UNKNOWN — TBD-01]) | [INFERRED] | I (TC-WB-006) — blocked by TBD-01 |
| BR-033 | Protocol = 769, game version = "1.21.4". | Compatibility | `src/_copybooks/DD-VERSION` | [CONFIRMED] | U (TC-VR-001) |
| BR-034 | Offline UUID = first 16 bytes of username, zero-padded. | Identity | `src/players/Players-NameToUUID.cob` | [CONFIRMED] | U (TC-ID-001) |
| BR-035 | **Target.** Unsupported loot functions (`apply_bonus`, `copy_components`, `copy_state`) and entry type `minecraft:dynamic` shall be rejected at build time with an explicit diagnostic. | Validation (Target) | `codegen/generators/blocks_loot_table/*` | [INFERRED — current source uses TODO/CONTINUE] | U negative (TC-CG-008) after closure |
| BR-036 | Multi-choice shapeless recipes (> 1 choice/tag/array ingredient) are rejected by the build-time recipe parser. | Validation | `src/parsers/Parse-Recipe-Shapeless.cob` | [CONFIRMED] | U negative (TC-PR-003) |
| BR-037 | **Target.** Empty or whitespace-only `/say` messages shall be rejected with `LK-PRINT-USAGE = 1`. | Input validation (Target) | `src/commands/RegisterCommand-Say.cob` | [UNKNOWN — current behavior not characterized, TBD-09] | U (TC-CMD-005) after closure |
| BR-038 | All commands set `LK-PRINT-USAGE = 1` on argument-count / literal-type mismatches enforced by the parser tree. | Input validation | `src/commands/*` | [CONFIRMED] | U (TC-CMD-009) |
| BR-039 | **Target.** Command input exceeding declared buffer lengths or containing invalid UTF-8 shall be rejected with `LK-PRINT-USAGE = 1`. | Input validation (Target) | `src/commands/*` | [UNKNOWN — not currently enforced] | F (TC-CMD-009-F) after closure |
| BR-040 | Player NBT persists inventory slots 0 and 2..45 (slot 1, crafting output, is excluded) with item IDs serialized as registry strings. | Persistence | `src/players/Players-SavePlayer.cob` | [CONFIRMED] | U (TC-PL-003a) |
| BR-041 | `Players-Connect` returns `LK-PLAYER-ID = 0` when no slot is free. | Capacity | `src/players/Players-Connect.cob` | [CONFIRMED] | U (TC-PL-001) |
| BR-042 | Only clients in `CLIENT-STATE-PLAY` receive tick-driven state packets (e.g., `SetHealth`). | Behavior | `src/players/Players-Tick.cob` | [CONFIRMED] | U (TC-PL-005a) |

---

## 7. External Interfaces

### 7.1 File Interfaces

| Interface | Path | Direction | Format | Program | Evidence |
|---|---|---|---|---|---|
| Player data | `<level>/playerdata/<uuid>.dat` | R/W | gzip NBT | `Players-SavePlayer`, `Players-LoadPlayer` | [CONFIRMED] |
| Level data | `<level>/level.dat` | R/W | gzip NBT | `src/world/*` (paragraph [UNKNOWN — TBD-05]) | [INFERRED] |
| Region | `<level>/region/r.<x>.<z>.mca` | R/W | Region container | `World-SaveChunk` → `Region-WriteChunkData` | [CONFIRMED] |
| Entity region | `<level>/entities/r.<x>.<z>.mca` | R/W | Region container | `World-SaveChunk` | [CONFIRMED] |
| Registries | `<datadir>/generated/reports/registries.json` | R | JSON | `CG-LoadRegistries` | [CONFIRMED] |
| Items | `<datadir>/generated/reports/items.json` | R | JSON | `CG-Items-Main` | [CONFIRMED] |
| Block loot tables | `<datadir>/generated/data/minecraft/loot_table/blocks/*.json` | R | JSON | `CG-BlocksLootTable-Main` | [CONFIRMED] |
| Emitted sources | `<outdir>/*.cob` | W | COBOL source | Generators | [CONFIRMED] |
| Whitelist file | `<level>/whitelist.*` [UNKNOWN — TBD-06] | R/W | [UNKNOWN — TBD-06] | `Whitelist-Read`, `-Add`, `-Remove` | [CONFIRMED — programs] / [UNKNOWN — format] |
| Server properties | `server.properties` | R/W | `key=value` | `ServerProperties-Serialize`, `-Deserialize`, `-Write` | [CONFIRMED] |

### 7.2 Inter-Program Calls (Key)
- Players → World (`World-FindSpawnLocation`, `World-SetBlock`, `World-GetBlockEntity`), Players → Packets (`SendPacket-*`), Players → Chat.
- World / Chunk → NBT encoder/decoder, Region library (`Region-WriteChunkData`), Callbacks (`GetCallback-*`, `SetCallback-*`).
- Commands → Players, World, Whitelist, ServerProperties.
- Inventory → Items, Recipes, Packets, World (drop).
- Entities → Inventory, Packets, World, collision helpers.

### 7.3 Network Protocol
- Module path: `src/packets`. Direction constants: `PACKET-DIRECTION-CLIENTBOUND = 0`, `PACKET-DIRECTION-SERVERBOUND = 1`. [CONFIRMED]
- Per-packet wire contracts, malformed-frame resilience, and authentication/handshake sequencing: [UNKNOWN — TBD-02].
- **Dependency Note:** Downstream FRs that depend on packet behavior (FR-PL-005 `SetHealth`, FR-WB-003 broadcast, FR-EN-003 `TakeItemEntity`) are specified **at message-name granularity only** until TBD-02 is closed. Byte-layout contracts are explicitly out of scope for approval in this revision and must not be implemented against the PRD until TBD-02 closure.

### 7.4 External Native Functions
- Compression: `ZlibCompress`, `ZlibDecompress`, `GzipCompress`, `GzipDecompress`. [CONFIRMED]
- Hashing: `SHA1-*`; arithmetic helper `LeadingZeros32`. [CONFIRMED]
- File I/O: `CBL_CREATE_DIR`, `CBL_CREATE_FILE`, `CBL_WRITE_FILE`, `CBL_CLOSE_FILE`, `Files-ReadAll`, `Files-WriteAll`. [CONFIRMED]
- Directory I/O: `OpenDirectory`, `ReadDirectory`, `CloseDirectory`. [CONFIRMED]
- Time: `SystemTimeMicros`. [CONFIRMED]

---

## 8. Non-Functional Requirements

NFRs are quantified with targets, measurement methods, and owner roles. Each NFR is labelled **Current-Baseline** (enforceable against existing code) or **Target-State** (requires implementation hooks delivered alongside v1). Reference environment: 4 vCPU / 8 GB RAM / SSD unless stated.

### 8.1 Performance (Target-State unless noted)

| ID | Requirement | Target | Measurement | Owner | Class |
|---|---|---|---|---|---|
| NFR-P-001 | Tick rate at ≤ 10 concurrent players on default world | ≥ 20 TPS sustained; no tick > 100 ms p99 | Tick-duration histogram exported via NFR-OBS-002 | Runtime Eng. | Target |
| NFR-P-002 | Command response time (local) | p95 ≤ 50 ms, p99 ≤ 150 ms | End-to-end command benchmark | Runtime Eng. | Target |
| NFR-P-003 | `/save` completion for baseline world (≤ 256 dirty chunks, ≤ 10 players) | p95 ≤ 2 s, p99 ≤ 5 s | Benchmark harness | Runtime Eng. | Target |
| NFR-P-004 | Packet processing budget per tick | ≤ 25 ms of 50 ms tick window at nominal load | Profile of packet I/O stage | Protocol Eng. | Target (blocked by TBD-02) |
| NFR-P-005 | Code generator wall-clock on reference dataset | ≤ 60 s | CI timing | Codegen Eng. | Current-Baseline |

### 8.2 Scalability

| ID | Requirement | Target | Measurement | Owner | Class |
|---|---|---|---|---|---|
| NFR-S-001 | Max concurrent players meeting NFR-P-001 | 10 (default cap per BR-020) | Load test | Runtime Eng. | Current-Baseline (cap) / Target (perf) |
| NFR-S-002 | Max loaded chunks | ≥ 441 (21×21 around a player) without TPS regression | Load test | Runtime Eng. | Target |
| NFR-S-003 | Max active entities | ≥ 2,000 across the world without TPS regression | Load test | Runtime Eng. | Target |
| NFR-S-004 | Max whitelist entries | 10,000 persisted with `list` response ≤ 200 ms | Benchmark | Runtime Eng. | Target (bounded by chunk/JSON buffer limits in §8.4) |

### 8.3 Reliability

| ID | Requirement | Target | Measurement | Owner | Class |
|---|---|---|---|---|---|
| NFR-R-001 | Autosave durability | No data loss for changes > 60 s old on clean shutdown; ≤ 60 s loss window on crash | Fault-injection harness | SRE | Target |
| NFR-R-002 | Region file crash-consistency | No partial `.mca` on power-loss (temp + rename pattern) | Fault injection | Runtime Eng. | Target |
| NFR-R-003 | MTTR after process crash | ≤ 60 s (auto-restart + warmup) | Chaos test | SRE | Target |
| NFR-R-004 | Assertion-driven exit rate in steady state | 0 per 7-day soak | NFR-OBS-002 metric | Runtime Eng. | Target |
| NFR-R-005 | Graceful tolerance of a corrupt player file | Load returns defaults; event logged; process does not crash | Unit test | Runtime Eng. | Current-Baseline (defaults returned) / Target (quarantine, R-M-008) |

### 8.4 Capacity and Limits (Current-Baseline)

| Limit | Value | Source |
|---|---|---|
| Inventory slots | 46 | `DD-PLAYERS` [CONFIRMED] |
| Test failure buffer | 100 | `TestMain` [CONFIRMED] |
| Template variables | 16 per template | `codegen/common/template.cob` [CONFIRMED] |
| Region directory listing | 4,096 names | Region code [CONFIRMED] |
| Chat message (`/say`) | 1,024 bytes | `RegisterCommand-Say` [CONFIRMED] |
| General string buffer | 255 bytes | Widely used [CONFIRMED] |
| JSON input buffer | 10,000,000 bytes | `DD-CODEGEN-JSON` [CONFIRMED] |
| Chunk save buffer | 1,048,576 bytes | `World-SaveChunk` [CONFIRMED] |
| Player NBT buffer | 64,000 bytes | `Players-SavePlayer` [CONFIRMED] |
| VarInt decode | ≤ 5 bytes (32-bit) | `Decode-VarInt` [CONFIRMED] |

Scalability targets in §8.2 must remain within these limits; any exceedance requires either a buffer increase or streaming rewrite.

### 8.5 Security

| ID | Requirement | Target | Measurement | Owner | Class |
|---|---|---|---|---|---|
| NFR-SEC-001 | Whitelist enforcement | 100% of non-whitelisted connect attempts rejected when enabled | Integration test | Security Eng. | Target |
| NFR-SEC-002 | Identity spoofing resistance | v1 is offline-only and must be documented as such; v2 introduces Mojang session authentication (R-H-001) | Design review | Security Eng. | Target |
| NFR-SEC-003 | Command authorization | Console-only commands refuse without explicit target (`/kill`, `/gamemode`) | Unit test | Runtime Eng. | Current-Baseline |
| NFR-SEC-004 | Buffer hardening | No write beyond declared PIC length; enforced via pre-write length guards and fuzz testing | Fuzz | QA | Target (linked to R-H-002) |
| NFR-SEC-005 | File path safety | Player/region paths must reject traversal (`..`, absolute paths) | Unit test | Runtime Eng. | Target (enforcement logic [UNKNOWN] in current source) |

### 8.6 Observability (Target-State)

| ID | Requirement | Target | Measurement | Owner | Class |
|---|---|---|---|---|---|
| NFR-OBS-001 | Structured logs for connect, disconnect, damage, save, command | 100% of events logged with client_id, player_uuid, outcome | Log-schema review | Runtime Eng. | Target |
| NFR-OBS-002 | Metrics: TPS, tick duration, save duration, chunk-load count, entity count, assertion count | Exported via a metrics file or log scraper at ≥ 0.1 Hz | Integration test | SRE | Target |
| NFR-OBS-003 | Health check | Exit code + heartbeat file updated ≥ every 5 s while ticking | Integration test | SRE | Target |
| NFR-OBS-004 | Audit events for `/whitelist`, `/stop`, `/save` | 100% captured with actor identity and parameters | Integration test | Security Eng. | Target |

Current source does not include a metrics exporter; delivering §8.6 requires new instrumentation hooks as part of implementation.

### 8.7 Testability

| ID | Requirement | Target | Measurement | Owner | Class |
|---|---|---|---|---|---|
| NFR-T-001 | Verification matrix coverage | 100% of FRs and BRs mapped to ≥ 1 test case | Traceability matrix (Appendix B) | QA | Current-Baseline |
| NFR-T-002 | Unit test pass rate in CI | 100% on main branch | CI gate | QA | Current-Baseline |
| NFR-T-003 | Fuzz coverage for parsers (NBT, JSON, VarInt, command) | ≥ 24 h without new crashes per release | Fuzz harness (new) | QA | Target (requires new harness) |
| NFR-T-004 | Golden-file stability for generated code | Byte-identical on reference input | CI gate | Codegen Eng. | Current-Baseline |

### 8.8 Compatibility

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR-C-001 | Minecraft version | Protocol 769 / 1.21.4 | `DD-VERSION` [CONFIRMED] |
| NFR-C-002 | Persistence formats | NBT, region v1, gzip | `Region-*`, `Players-*` [CONFIRMED] |
| NFR-C-003 | COBOL dialect | GnuCOBOL with `BINARY-CHAR`, `ANY LENGTH`, `OCCURS DEPENDING ON`, `PROGRAM-POINTER`, `ALLOCATE`/`FREE` | Source-wide [CONFIRMED] |
| NFR-C-004 | GnuCOBOL version | ≥ 3.2 enables bitwise branch; < 3.2 uses arithmetic fallback | `src/encoding` [CONFIRMED] |

### 8.9 Maintainability
- Code generation isolates upstream data changes to emitted files. [CONFIRMED]
- EXTERNAL state in copybooks centralizes mutation for a single-threaded runtime. [CONFIRMED]
- Callback pointer tables permit per-item/block/state behavior registration. [CONFIRMED]

### 8.10 Internationalization
- Out of scope for v1 (Section 1.5); no locale layer observed. [INFERRED]

### 8.11 Legacy System Limitations (Documented)
- Single-threaded runtime due to EXTERNAL shared state. [INFERRED]
- Fixed-size buffers with no dynamic growth for JSON (10 MB), chunk save (1 MB), and player NBT (64 KB). [CONFIRMED]
- Assertion-based termination on data errors rather than structured recovery. [CONFIRMED]
- VarInt decode limited to 32-bit. [CONFIRMED]
- Offline UUID derivation only. [CONFIRMED]
- Persistence is untagged by schema version; any on-disk format change is a breaking change unless a version tag is introduced (see R-M-009).

---

## 9. Risks & Mitigations

Each risk is rated, owned, and assigned a mitigation, trigger, contingency, and residual rating.

### 9.1 HIGH Risks

| ID | Risk | Rating | Owner | Mitigation | Trigger | Contingency | Residual |
|---|---|---|---|---|---|---|---|
| R-H-001 | Offline UUID collisions / identity spoofing via `Players-NameToUUID`. | HIGH | Security Eng. | Document v1 as offline-only; design v2 online-mode with Mojang session auth; detect duplicate UUIDs at connect and reject. | Duplicate UUID observed in connect log. | Refuse connect; alert operator; hotfix name-collision guard. | MEDIUM |
| R-H-002 | Silent truncation on fixed buffers (JSON 10 MB, chunk 1 MB, player NBT 64 KB, `X(255)` strings). | HIGH | Runtime Eng. | Add pre-write size checks; emit structured error and refuse the operation on overflow; expose `buffer_overflow_total` metric. | Overflow metric > 0 or assertion in encode path. | Rotate to larger buffer; block save; investigate payload. | MEDIUM |
| R-H-003 | Codegen emits silent TODO/no-op branches for unsupported loot features instead of failing the build. | HIGH | Codegen Eng. | Implement BR-035 target: replace TODO/CONTINUE paths with explicit asserts and descriptive diagnostics; add fixtures per unsupported feature. | Upstream data drop containing an unsupported feature proceeds without diagnostic. | Pin last known-good data; prioritize parser hardening. | MEDIUM until BR-035 closed |
| R-H-004 | Shapeless parser rejects multi-choice recipes (data gap). | HIGH | Codegen Eng. | Enforce BR-036 at build; extend parser in v1.1 to handle multi-choice; add a pre-build linter over upstream data. | Build fails on an upstream drop. | Pin last good data; schedule parser enhancement. | LOW |
| R-H-005 | Assertion-driven termination provides minimal diagnostics. | HIGH | Runtime Eng. | Enrich `ASSERT-FAILED` with program, paragraph, and variable snapshot context; route to structured logs; publish a runbook. | Assertion exit in production. | Restart service; file incident with captured context. | MEDIUM |
| R-H-006 | Packet internals not fully analyzed; malformed-packet resilience unknown. | HIGH | Protocol Eng. | Close TBD-02 via full extraction; add fuzz harness on serverbound packets; add size guards on every decoder. | Crash or hang on malformed packet. | Rate-limit and disconnect client; hotfix decoder. | MEDIUM until TBD-02 closed |
| R-H-007 | Evidence-integrity risk: requirements drift from actual source behavior (incorrect confidence tags). | HIGH | Product Architect | Mandatory re-audit of `[CONFIRMED]` tags each revision; require source-snippet cross-reference in a signed Evidence Appendix before sign-off. | Reviewer flags an unsupported `[CONFIRMED]` claim. | Downgrade tag; revise dependent FR/BR; reissue. | MEDIUM |

### 9.2 MEDIUM Risks

| ID | Risk | Rating | Owner | Mitigation | Trigger | Contingency | Residual |
|---|---|---|---|---|---|---|---|
| R-M-001 | Hard-coded gameplay constants (world bounds, fall threshold, regen, expiry). | MEDIUM | Runtime Eng. | Externalize to `server.properties` or a dedicated config in v1.1. | Upstream rebalancing. | Temporary code patch; release. | LOW |
| R-M-002 | No i18n for chat and death messages. | MEDIUM | Runtime Eng. | Add message catalog in v1.1; mark strings for extraction. | Locale requirement. | Accept English-only. | LOW |
| R-M-003 | Sign deserialization skips top-level unknown tags with TODO. | MEDIUM | Runtime Eng. | Complete packed/base-class handling; log skipped tags. | Data-loss reports. | Emit warning; backfill handler. | LOW |
| R-M-004 | Inventory slot-1 exclusion relies on remap correctness (BR-040). | MEDIUM | Runtime Eng. | Round-trip unit tests per slot; property-based tests. | Slot mismatch observed. | Patch mapper; restore from backup. | LOW |
| R-M-005 | Single-threaded assumption via EXTERNAL global state. | MEDIUM | Architecture | Keep single-threaded in v1; document the invariant; gate any future refactor behind design review. | Performance cap hit. | Vertical scale; schedule refactor. | MEDIUM |
| R-M-006 | `/say` empty-message handling is undefined (BR-037 target). | MEDIUM | Runtime Eng. | Characterize current behavior (TBD-09); implement target-state rejection. | Empty broadcasts or spam in test. | Hotfix. | LOW after closure |
| R-M-007 | Command-input hygiene beyond argument count is not enforced (BR-039 target). | MEDIUM | Runtime Eng. | Implement explicit length and UTF-8 checks in parser; add fuzz harness. | Fuzz finds crash/corruption. | Disable affected command; hotfix. | LOW after closure |
| R-M-008 | Corrupt player-file handling (truncated files, invalid-gzip-with-non-gzip-payload, partial NBT). | MEDIUM | Runtime Eng. | Validate magic + length; on failure return defaults and quarantine the file to `<uuid>.dat.bak.<ts>`. | Read error or checksum fail. | Restore from backup; notify admin. | LOW |
| R-M-009 | Persistence format evolution without explicit schema versioning. | MEDIUM | Architecture | Add a `DataVersion` field at the NBT root; maintain a migration table in the loader. | Version mismatch detected. | Refuse load with guidance. | MEDIUM |
| R-M-010 | Native-dependency variance (zlib/gzip/file APIs) across platforms. | MEDIUM | DevOps | Pin the runtime image; CI matrix across supported platforms; smoke-test compression round-trip. | CI failure. | Freeze build; investigate. | LOW |
| R-M-011 | Operational runbook gaps (backup/restore, region corruption recovery, rollback). | MEDIUM | SRE | Author runbooks before GA; validate in chaos drills. | Incident without runbook. | Ad-hoc response. | LOW |
| R-M-012 | Registry ID edge semantics (0/negative) inconsistently handled across call sites. | MEDIUM | Runtime Eng. | Add a shared `Registry-ValidateID` helper; enforce `> 0` at entry points; audit all callers. | Assertion on zero/negative ID. | Patch offending call site. | LOW |
| R-M-013 | Command authorization model conflates syntax with privilege for most commands. | MEDIUM | Runtime Eng. | Introduce an explicit permission gate per command (console/operator/player); extend parser tree annotations. | Unauthorized invocation observed. | Restrict command; patch gate. | LOW |

### 9.3 LOW Risks

| ID | Risk | Rating | Owner | Mitigation | Trigger | Contingency | Residual |
|---|---|---|---|---|---|---|---|
| R-L-001 | Only 100 failure records retained by the test runner. | LOW | QA | Raise the cap or stream to a file in diagnostic builds. | Truncation observed. | Rerun a focused subset. | LOW |
| R-L-002 | Whitelist `list` requires `ALLOCATE`/`FREE` pairing. | LOW | Runtime Eng. | Code-review checklist; leak test. | Memory growth. | Restart. | LOW |
| R-L-003 | Codegen optimizer applies only narrow patterns. | LOW | Codegen Eng. | Accept; extend as needed. | Build-size regression. | Tune patterns. | LOW |
| R-L-004 | VarInt decode is capped at 32-bit. | LOW | Protocol Eng. | Accept; document. | 64-bit requirement emerges. | Implement VarLong. | LOW |

### 9.4 Open Items Requiring Source Closure

| ID | Item | Required Action | Impact |
|---|---|---|---|
| TBD-01 | Spawn-chunk unload-protection implementation | Extract from `src/world/*`; update FR-WB-006 and BR-032 with paragraph-level citations. | Unblocks FR-WB-006/BR-032 verification. |
| TBD-02 | Packet internals in `src/packets` | Extract per-packet contracts; update §7.3 and dependent FRs; unblock R-H-006 closure. | Unblocks protocol NFRs and fuzzing. |
| TBD-03 | Remaining `DD-*` copybook PIC/USAGE (`DD-SERVER-PROPERTIES`, `DD-WORLD`, `DD-CHUNK-REF`, and `DD-PLAYERS` food/experience) | Extract; populate Section 4.2 [UNKNOWN] cells. | Unblocks migration type fidelity. |
| TBD-04 | `src/encoding` complete routine inventory (hex, UUID, inventory-slot, position) | Extract; add per-routine FRs where behavior is contractual. | Improves test coverage and traceability. |
| TBD-05 | `level.dat` exact path and schema | Extract from `src/world`; confirm location and format. | Completes §7.1 row. |
| TBD-06 | Whitelist on-disk format | Extract from `Whitelist-Read/Add/Remove`. | Unblocks migration, backup, and NFR-S-004 sizing. |
| TBD-07 | Template engine behavior for unbound `$var$` placeholder | Add characterization test; update FR-CG-003 Negative Acceptance. | Unblocks template-contract correctness. |
| TBD-08 | Respawn transition in player lifecycle | Identify source for respawn path; update FR-PL-008 or downgrade the transition. | Unblocks state-machine completeness. |
| TBD-09 | `/say` empty-message current behavior | Characterize; implement BR-037 target if absent. | Unblocks BR-037 closure. |

**Approval gate:** TBD-01, TBD-02, TBD-03, TBD-07, TBD-08, and TBD-09 must be closed before implementation commit on protocol, persistence, lifecycle, or type-sensitive components. An Evidence Appendix (see Appendix C) shall accompany any revision that changes requirement text or evidence tags.

---

## Appendix A — Capability → Source Map (with confidence)

| Capability | Primary Program(s) | Module | Confidence |
|---|---|---|---|
| Codegen orchestration | `CodegenMain` | `codegen/` | [CONFIRMED] |
| Template engine | `Codegen-TemplateLoad`, `Codegen-TemplateEval`, `Codegen-Optimize` | `codegen/common/` | [CONFIRMED] (unknown-transform path); [UNKNOWN — TBD-07] (unbound-variable path) |
| Registry loading | `CG-LoadRegistries` | `codegen/data/` | [CONFIRMED] |
| Player lifecycle | `Players-Init/Connect/Disconnect/Save/SavePlayer/LoadPlayer/Tick/HandleMove/Damage` | `src/players/` | [CONFIRMED]; respawn path [INFERRED — TBD-08] |
| World mutation | `World-CheckBounds/GetBlock/SetBlock/SaveChunk` | `src/world/` | [CONFIRMED] |
| Spawn-chunk protection | `src/world/*` | `src/world/` | [INFERRED — TBD-01] |
| Block behaviors | `RegisterBlock-*` | `src/blocks/` | [CONFIRMED] |
| Block entities | `RegisterBlockEntity-Sign`, `BlockEntity-Sign-Update` | `src/blockentities/` | [CONFIRMED] |
| Entities | `RegisterEntity-Generic/Item`, `EntityBase-Serialize/Deserialize` | `src/entities/` | [CONFIRMED] |
| Inventory / crafting | `Inventory-*`, `RegisterWindow-*` | `src/inventory/` | [CONFIRMED] |
| Recipe parsing | `Parse-Recipe-Result/Shaped/Shapeless` | `src/parsers/` | [CONFIRMED] |
| Commands | `RegisterCommand-*` | `src/commands/` | [CONFIRMED]; UTF-8/length hygiene [UNKNOWN] |
| Chat | `SendChatMessage`, `BroadcastChatMessage(Except)` | `src/util/` | [CONFIRMED] |
| Encoding | `Decode-*`, `Encode-*`, `Hex-*`, `SHA1-*`, `UUID-*` | `src/encoding/` | [CONFIRMED — module] / [UNKNOWN — full routine set per TBD-04] |
| Packets | packet handlers | `src/packets/` | [CONFIRMED — module] / [UNKNOWN — internals per TBD-02] |
| Test framework | `TestMain`, `TestSuite*/TestUnit*/TestCase*/TestAssert*` | `tests/` | [CONFIRMED] |

---

## Appendix B — Verification Traceability Matrix (Summary)

| FR / BR | Source Program | Key Variables / Copybook Fields | Test Type | Test Case ID |
|---|---|---|---|---|
| FR-CG-001 / BR-001 | `CodegenMain` | `DATADIR`, `OUTDIR`, `TPLDIR` | U | TC-CG-001 |
| FR-CG-002 / BR-002 | `CG-LoadRegistries` | `DD-REGISTRIES`, `REGISTRY-NAME`, `REGISTRY-ENTRY-NAME` | U | TC-CG-002 |
| FR-CG-003 | `Codegen-TemplateLoad/Eval/Optimize` | `REPLACE-PTR`, template buffer | U | TC-CG-003 (+ TC-CG-003b after TBD-07) |
| FR-CG-004..007 / BR-030/031 | Generators | Emitted `.cob` artifacts | G / U | TC-CG-004..007 |
| FR-CG-007 / BR-035 (Target) | Loot generator | TODO branches → asserts | U neg. | TC-CG-008 (after R-H-003 closure) |
| FR-PL-001 / BR-041 | `Players-Connect` | `PLAYER-CLIENT`, `LK-PLAYER-ID` | U | TC-PL-001 |
| FR-PL-002 | `Players-Disconnect` | Window callback pointer | U | TC-PL-002 |
| FR-PL-003 / BR-003 / BR-040 | `Players-SavePlayer` | Inventory-slot mapping, NBT buffer | I | TC-PL-003 (+ TC-PL-003a) |
| FR-PL-004 / BR-004 | `Players-LoadPlayer` | Gzip magic, NBT root | U | TC-PL-004 |
| FR-PL-005 / BR-015/016/042 | `Players-Tick` | `PLAYER-HEALTH`, `PLAYER-HURT-TIME` | U | TC-PL-005/006/005a |
| FR-PL-006 / BR-017 | `Players-HandleMove` | `PLAYER-FALL-DISTANCE`, `flying` | U | TC-PL-006a |
| FR-PL-007 / BR-018 | `Players-Damage` | Immunity-matrix inputs | U | TC-PL-007 |
| FR-PL-008 | Composite | Player state | I | TC-PL-008 (respawn pending TBD-08) |
| FR-WB-001 / BR-005 | `World-CheckBounds` | Y | U | TC-WB-001 |
| FR-WB-002 | `World-GetBlock` | Chunk lookup | U | TC-WB-002 |
| FR-WB-003 / BR-006 | `World-SetBlock` | Section counters | U | TC-WB-003 |
| FR-WB-004 / BR-026 | `World-SaveChunk` | Dirty flags, palette | I | TC-WB-004 |
| FR-WB-005 / BR-023/024 | `RegisterBlock-*` | Block callback table | U | TC-WB-005 |
| FR-WB-006 / BR-032 | `src/world/*` [TBD-01] | Spawn chunk set | I | TC-WB-006 (blocked) |
| FR-IC-001..005 / BR-007/008/025 | `Inventory-*`, `RegisterWindow-*` | Slot array, NBT | U / I | TC-IC-001..005 |
| FR-CMD-001..008 / BR-009/010/019/038 | `RegisterCommand-*` | `LK-PRINT-USAGE` | U | TC-CMD-001..008 |
| FR-CMD-005 / BR-037 (Target) | `RegisterCommand-Say` | Message buffer | U | TC-CMD-005 (after TBD-09) |
| FR-CMD-009 / BR-039 (Target) | Command parser tree | Buffer-length, UTF-8 guards | F | TC-CMD-009-F (after implementation) |
| FR-EN-001..003 / BR-011 | `RegisterEntity-*` | Item-entity fields | U | TC-EN-001..003 |
| FR-CH-001/002 / BR-013/014 | `chat.cob` | Client-state gate | U | TC-CH-001/002 |
| FR-SP-001..003 / BR-020/021 | `ServerProperties-*` | `DD-SERVER-PROPERTIES` | U | TC-SP-001..003 |
| FR-RG-001 / BR-022 | `Region-RegionFileName` | Path composition | U | TC-RG-001 |
| FR-TS-001..003 / BR-012 | `tests/test.cob`, `TestMain` | `FAILED-TESTS` | Self | TC-TS-001..003 |
| BR-027 | `Decode-VarInt` | Byte count | U | TC-EC-001 |
| BR-028/029/036 | `Parse-Recipe-*` | Recipe buffers | U | TC-PR-001..003 |
| BR-033 | `DD-VERSION` | Protocol/version constants | U | TC-VR-001 |
| BR-034 | `Players-NameToUUID` | UUID derivation | U | TC-ID-001 |

---

## Appendix C — Evidence Appendix (Required Before Sign-Off)

The Evidence Appendix shall accompany any revision that changes requirement text or evidence tags. For each requirement and business rule, it shall list:

1. Requirement/BR ID.
2. Source program file and the minimal snippet or paragraph identifier that supports the claim.
3. The exact evidence tag (`[CONFIRMED]`, `[INFERRED]`, `[UNKNOWN]`) and justification.
4. Linked TBD ID if closure is required.

This appendix is not populated in the current revision because TBD-01..TBD-09 are open; it shall be produced as part of the Approval Gate defined in Section 9.4.

---

*End of PRD. Items marked [UNKNOWN] or referenced by TBD-01 through TBD-09 require targeted source extraction before the corresponding components are approved for implementation.*
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
