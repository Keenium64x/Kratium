# Kratium Agent Notes

Use the global Codex operating contract at `/home/keenan/.codex/AGENTS.md` as the primary working method.
For substantial input-system work, use `/home/keenan/.codex/working_method/DEEP_DEVELOPMENT_PROTOCOL.md`.

## Project Memory

- Primary durable memory: `/mnt/c/Users/7keen/OneDrive/Ai Memory/Projects/Kratium/PROJECT_MEMORY.md`.
- Local handoff memory: `docs/PROJECT_MEMORY.md`.
- Input-system map: `docs/input_system/INPUT_SYSTEM_MAP.md`.
- User capability index for this project: `docs/USER_CAPABILITY_INDEX.md`.

## Input System Rules

- Active file: `kratium/input_system.py`.
- Older/reference file: `kratium/input_system1.py`.
- Before changing the input layer, read the input-system map and inspect only relevant symbols.
- Preserve the factory structure: top-level process → station functions → subfunctions → explicit input/output plumbing.
- Update the input-system map when station responsibilities or plumbing change.

## Validation Defaults

- Backend Python: compile touched modules first.
- Frappe state/schema: use focused `bench --site kratium.localhost ...` checks from `/home/keenan/Kratium`.
- Frontend: validate from `frontend/` with focused Yarn commands.
