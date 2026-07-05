# Kratium Project Memory

## Current Project State

- Active project: Kratium, a personal management system built as a Frappe app.
- Active area: input system / AI orchestration layer.
- Current stage: process reset and structural planning before further implementation.
- Main source file: `kratium/input_system.py`.
- Supporting/older source file: `kratium/input_system1.py`.

## Operating Direction

- The user wants top-down development like designing a factory: start with the large process, then define stations, then define subfunctions, then define input/output plumbing, then write exact code.
- The assistant should educate while designing, not disappear into implementation.
- Before significant code is written, the user should understand the function being added, why it exists, what enters it, what leaves it, and where the result goes.
- The assistant may derive subfunctions and plumbing when delegated, but must explain the structure afterwards in system terms.
- The assistant should ask more focused questions before, during, and after large design/implementation passes.

## Input System Summary

- Current `input_system.py` is a large implemented orchestration file with regions for input streams, orchestration, execution bus, and tools.
- Current pipeline starts at `start_orchestration(final_input)`, creates `OrchestrationState`, and passes it to `run_orchestrator(state)`.
- Orchestrator stage tools include clarification, information collection, route selection, implementation design, execution, and review.
- The execution bus prepares operations, requests approvals, syncs approved actions, and returns execution reports.
- Utility tools read Frappe system state, DocType metadata, records, dates, action context, and public web information.

## Decisions

- Keep `AGENTS.md` lean and move detailed operating references into focused docs to reduce recurring token usage.
- Use `docs/input_system/INPUT_SYSTEM_MAP.md` as the task-specific structure and plumbing source of truth.
- Use `docs/USER_CAPABILITY_INDEX.md` to track what coding concepts/functions the user has covered.
- Use Trilium only when explicitly requested for note creation/update, or when reading style/context is necessary for a learning tangent.

## Open Questions

- Decide whether `input_system.py` should remain one file for now or be split into modules after the structure is understood.
- Decide the first input-system slice to redesign together: input streams, orchestration, execution bus, tools, or knowledge capture.
- Decide which parts of the current implementation are accepted working machinery and which parts should be treated as experimental.
