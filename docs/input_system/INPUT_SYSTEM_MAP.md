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
- `get_action_blueprint_agent()`
- `expand_action_implementation_blueprint(text, blueprint)`
- `compile_action_blueprint_execution_plan(text, blueprint)`
- `design_implementation(ctx)`
- `request_user_clarification(state, clarification)`
- `compile_execution_plan(state)`
- `handoff_to_execution_bus(state, plan)`
- `resume_orchestration(state, new_information)`

Clarification boundary:
- clarification should ask for missing implementation details, not security permission;
- random/any choices requested by the user should flow into route and implementation as AI decisions;
- destructive risk is handled by the execution bus security review and approval prompts, not by pausing route selection.

Progressive design interview:
- large structured prompts can run a one-question-at-a-time interview before route selection;
- simple batch operation prompts such as “create 10 actions then delete 3” skip the interview and go straight to orchestration/security;
- the interview now builds a `DesignInformationMap` before choosing a question;
- active question choice is owned by `DesignQuestionPlannerDecision`, an AI planning station, not by a hardcoded naming/timing/content checklist;
- deterministic map code may estimate scope, extract obvious terms, validate outputs, and provide provider-failure fallback, but normal question wording and readiness decisions should come from the AI planner;
- broad design prompts with no prior design answer and a high-impact map gap must ask one implementation-map question before blueprinting, unless the user explicitly says to decide/make assumptions/simple;
- the first design question must shape implementation structure such as hierarchy, parent/child levels, reusable templates vs generated instances, scale, timing/scheduling, naming, or assumptions; preference-only questions are rejected and retried;
- the map records goal, domain, scope, scale model, structure model, content model, timing model, naming model, DocType strategy, field intents, assumptions, unknowns, and readiness;
- the map now also records generic `implementation_requirements`; these are the contract the blueprint must preserve, replacing hardcoded workout/study validators;
- assumptions are explicit records with confidence, impact, category, and reason, rather than hidden defaults;
- question selection is driven by high-impact map unknowns instead of a fixed checklist;
- if the user explicitly asks to review assumptions, the map stops treating inferred answers as final for those assumptions and asks compact bundled questions until the important structure/content/timing/naming choices are recorded;
- broad design requests should resolve structure, naming, timing, content detail, and field assumptions through the generic information-map unknown/requirement mechanism, not prompt-specific routes;
- relevant Action field intents are mapped from DocType metadata where available, then marked as user-provided, inferred, assumed, ask, or skip;
- the interview first classifies scope/domain and estimates likely Action count range;
- before asking, the interview infers high-confidence scope/detail/structure/assumption answers directly from the prompt and adds them to the design brief;
- large regimes still ask high-impact scope questions such as minimum size, detail level, horizon, hierarchy, and naming when those decisions materially change operation count or Action tree shape;
- questions should not walk a fixed checklist; after one high-impact answer, infer downstream decisions where reasonable and ask again only if another unresolved decision still materially changes the build;
- each answer is stored, then the next question plan is recalculated so later questions can depend on earlier answers;
- AI Execution Console stores `question_plan`, `question_answers`, and `active_question_id` as hidden JSON/data fields;
- AI Execution Console rechecks stored `question_plan` before processing; stale interview state for prompts that now classify as simple batch operations is cleared and rerouted to execution/security;
- once the interview is complete, a design brief with answers, system assumptions, and the information map is appended to the prompt sent into orchestration/blueprint implementation.

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

Same-plan record references:
- create/update operations may put an earlier `operation_id` into writable Link/parent fields;
- `compile_execution_plan` normalizes those references into operation dependencies;
- sync resolves same-plan operation IDs to the real Frappe record names after the dependency succeeds;
- tree/hierarchy records should create parents before children, then children link to the parent operation ID;
- for `Action`, this supports `parent_action`/`ancestor`; for other DocTypes, sync uses DocType metadata to discover tree parent and Link fields.

Approval console behavior:
- approval prompts are recorded per security group;
- a user-requested manual approval test can force even low-risk groups to require approve/deny;
- approval/denial only records the decision and does not sync immediately;
- once every required group has a recorded decision, the request becomes ready to execute;
- sync runs approved operations and skips denied operation groups.
- `Ready to Execute` is an execution state: pressing Process from that state runs the sync path.
- stale approval decisions from older security plans are ignored; only current security group IDs count.
- execution preview/readable output should list the actual operations synced, including created/deleted record IDs.
- read-only search/list/show requests can complete in the console with information results instead of going through execution security.
- counted random Action requests must preserve counts; for example 10 creates and 3 deletes becomes 13 atomic operations.

Important boundary:
- orchestration designs intended operations;
- execution bus decides whether operations are safe enough to run and whether user approval is needed.

Action implementation model:
- Action-building requests now use an Action blueprint station before atomic operation compilation;
- the AI produces a compact `ActionImplementationBlueprint` with groups, repeated templates, target count, assumptions, and implementation notes;
- the blueprint station treats `information_map.implementation_requirements` as the implementation contract and must preserve those requirements through groups, templates, variables, assumptions, or notes;
- deterministic compiler code expands that blueprint into one `doctype.create` operation per Action record;
- template variables such as subject/week/activity become concrete names and may become real parent group Actions;
- abstract blueprint groups containing placeholders are not synced as literal placeholder records;
- this is the default Action creation path, not a special study/workout shortcut;
- do not add domain-specific validator/normalizer code to force a test prompt shape; add generic map requirements instead;
- the older one-shot `ImplementationDesign` model remains as fallback for non-Action or unsupported operation-family work.

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

## 2026-07-09 Clarification Planner Readiness Gate

Design-interview readiness is now owned by the AI planner plus a generic completeness gate, not by a fixed question budget.

Planner station contract:
- input: original prompt, prior answers, classified scope, current `DesignInformationMap`;
- output: `DesignQuestionPlannerDecision` with either one next question or a ready decision;
- decision: whether map dimensions are resolved, safely assumed, explicitly delegated, or still need the user;
- handoff: `apply_design_question_planner_decision` updates map readiness and passes the completed map to route/blueprint planning.

Generic readiness rules:
- broad designs cannot become ready just because one short answer was provided;
- a weak answer without delegation becomes another concise map-completion question;
- ready decisions must include dimension reviews for scope/scale, structure/relationships, timing, naming, content, fields, and assumptions;
- security remains outside clarification and belongs to execution/security approval.
