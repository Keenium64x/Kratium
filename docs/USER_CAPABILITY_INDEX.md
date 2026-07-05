# User Capability Index

## Purpose

This file tracks coding concepts, libraries, functions, and structures the user has covered enough to reason about during development.
It is not a full tutorial. It is an index for deciding when to explain something before using it heavily.

## How To Use

- Add an item when the user asks for an explanation, finishes a learning tangent, or explicitly accepts a concept as understood.
- Mark new or unfamiliar concepts as `Needs explanation` when they are important to current work.
- Link or name the Trilium note/draft if a reusable practical note exists.
- Keep entries short so the file stays useful for context injection.

## Status Labels

- `Covered`: the user has practical understanding.
- `Needs explanation`: pause and explain before relying on it heavily.
- `Draft note ready`: a note draft exists but has not been written to Trilium.
- `Trilium note exists`: reusable knowledge has been captured in Trilium.

## Covered

- Top-down function design: large process → stations → subfunctions → plumbing → implementation.
- Function-as-input-output mental model.
- VS Code region markers as visible code structure.

## Needs Explanation

- Pydantic `BaseModel`, `Field`, validation, and `model_dump` / `model_validate` usage in Kratium.
- PydanticAI `Agent`, `RunContext`, tools, output schemas, retries, usage limits, and message history.
- Frappe DocType metadata reading and safe record sync patterns.
- Async functions and why some input-system tools are `async def`.
- Shared state objects such as `OrchestrationState` and when mutation is acceptable.

## Trilium / Note Links

- No confirmed Kratium input-system practical notes recorded here yet.
