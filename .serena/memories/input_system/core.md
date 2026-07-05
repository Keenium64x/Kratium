# Input System Core

- Active source: `kratium/input_system.py`.
- Older/reference source: `kratium/input_system1.py`.
- Detailed structure/plumbing map: `docs/input_system/INPUT_SYSTEM_MAP.md`.
- User capability tracking: `docs/USER_CAPABILITY_INDEX.md`.
- Work top-down: input stream → orchestration stations → execution bus → utility tools → exact code.
- Before editing, inspect only relevant symbols; `input_system.py` is ~5k lines.
- Current high-level regions: INPUT STREAMS, ORCHESTRATION, EXECUTION BUS, TOOLS.
- Current main entry: `start_orchestration(final_input)` builds `OrchestrationState(stage="clarification")` then calls `run_orchestrator(state)`.
- Current stage tools include `clarify_request`, `collect_information`, `select_route`, `design_implementation`, and `review_outcome`.