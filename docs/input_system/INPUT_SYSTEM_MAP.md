# Input System Map

## Purpose

The input system turns a user's natural-language request into a controlled Kratium system outcome.
It should behave like a factory:

1. accept an input;
2. clarify what it means;
3. collect missing information;
4. choose a route;
5. design exact operations;
6. check safety and approval;
7. sync approved operations;
8. report what happened;
9. review whether the outcome is good.

## Current Stage

- Stage: structural/plumbing audit before further implementation.
- Current code exists, but the structure needs to be made understandable and controlled.
- Do not add more deep behaviour until the relevant factory station and its handoffs are understood.

## Current Top-Level Sections

### Input Streams

Current file section exists but is empty.

Intended responsibility:
- receive inputs from different sources such as direct API calls, UI, mobile, voice, scheduler, or future integrations;
- normalize those source-specific inputs into one internal `OrchestrationInput` shape;
- hand normalized input to orchestration.

Key missing decisions:
- which input sources matter first;
- whether all sources use the same orchestration path;
- what metadata each source must provide.

### Orchestration

Current responsibility:
- owns the reasoning workflow;
- keeps `OrchestrationState` as the shared process state;
- calls specialist stage tools;
- pauses when user clarification, network recovery, or usage limits block progress;
- produces either a user question, an execution plan, an execution result, or a final answer.

Current main flow:

```text
start_orchestration(final_input)
  → OrchestrationInput
  → OrchestrationState(stage="clarification")
  → run_orchestrator(state)
  → pydantic-ai orchestrator agent
  → stage tool calls
  → OrchestrationRunResult(output, state)
```

Important current station functions:
- `clarify_request(ctx)`
- `collect_information(ctx, question, reason, desired_output, source_scope, context)`
- `select_route(ctx)`
- `design_implementation(ctx)`
- `request_user_clarification(state, clarification)`
- `compile_execution_plan(state)`
- `handoff_to_execution_bus(state, plan)`
- `resume_orchestration(state, new_information)`

### Execution Bus

Current responsibility:
- accepts a planned list of operations;
- evaluates risk and permissions;
- groups approval prompts;
- queues ready/waiting/blocked operations;
- syncs approved operations into Frappe or other allowed systems;
- returns an execution report.

Current flow:

```text
execute_plan(plan)
  → prepare_execution(plan)
  → request_execution_approval(preparation)
  → apply_execution_approvals(preparation, decisions)
  → sync_approved_execution(plan, approval_result)
  → execute_atomic_action(operation)
  → AtomicSyncResult
  → ExecutionSyncReport / ExecutionReport
```

Important boundary:
- orchestration designs intended operations;
- execution bus decides whether operations are safe enough to run and whether user approval is needed.

### Tools

Current responsibility:
- stage tools perform broad reasoning stations;
- utility tools answer specific system/web questions.

Stage tools:
- clarification;
- information collection;
- route selection;
- implementation design;
- outcome review.

Utility tools:
- current user lookup;
- DocType listing/description/relationship discovery;
- date and datetime resolution;
- action queries and context lookup;
- generic system record query/search/read/count;
- public web search/page read.

## Function Planning Contract

Before adding or changing a function in the input system, define:

- Responsibility: what one job does this function own?
- Input: what information enters it?
- Output: what does it return?
- Decision: what choice, validation, or transformation does it own?
- Handoff: which function or section receives its output?
- Knowledge level: is this function already in the user's capability index, or should it be flagged for explanation?

## Plumbing Contract

Every station handoff should be visible as a simple input/output chain.

Use this shape during planning:

```text
Function A
  input: raw request
  output: normalized request
  handoff: Function B receives normalized request

Function B
  input: normalized request
  output: clarified intent or user question
  handoff: route selection receives clarified intent
```

Avoid hidden side effects unless the function's responsibility is explicitly to update shared process state.
When shared state is used, say which fields are read and which fields are written.

## Token-Lean Working Pattern

For each pass:

1. read this map;
2. inspect only the relevant symbols in `kratium/input_system.py`;
3. update only the station being worked on;
4. update this map if the station/plumbing changes;
5. update `docs/USER_CAPABILITY_INDEX.md` when new concepts need tracking.

Do not reread the whole input-system file unless absolutely necessary.
