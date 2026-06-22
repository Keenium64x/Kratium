import asyncio
import ipaddress
import json
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
import logfire
from bs4 import BeautifulSoup
from ddgs import DDGS
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent, ModelMessagesTypeAdapter, ModelRetry, RunContext, Tool, UsageLimits
from pydantic_ai.models.gemini import GeminiModel, GeminiModelSettings
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from pydantic_core import to_jsonable_python


# =============================================================================
# region INPUT STREAMS
# =============================================================================

# endregion INPUT STREAMS


# =============================================================================
# region ORCHESTRATION
# =============================================================================


# region 1. SETUP
CHEAP_MODEL = "gemini-3.1-flash-lite"
STRONG_MODEL = "gemini-3.1-pro-preview"
APP_DIRECTORY = Path(__file__).resolve().parent.parent
LOGFIRE_DIRECTORY = APP_DIRECTORY / ".logfire"

MODEL_SETTINGS = GeminiModelSettings(
	temperature=0,
	max_tokens=8192,
	timeout=45,
)

USAGE_LIMITS = UsageLimits(
	request_limit=12,
	tool_calls_limit=20,
	total_tokens_limit=100_000,
)

AI_READABLE_DOCTYPES = {
	"Action",
	"Action Category",
	"Action Time Entry",
	"Fact",
	"Grocery",
	"Grocery Bin",
	"Grocery Item",
	"Grocery Stock Entry",
	"Grocery Stock Ledger Entry",
	"Meal",
	"Meal Plan",
	"Reminder Master",
	"Storage Location",
	"UOM Conversion",
	"Unit of Measure",
}

SYSTEM_CONTEXT = {
	"application": "Kratium is a personal management system.",
	"identity": (
		"The authenticated person's identity is available through get_current_user. "
		"Do not search personal records to determine who the current user is."
	),
	"calendar": (
		"Kratium has one calendar. It is a view of Action records. "
		"Calendar events are Action records where event is enabled. "
		"An event can be deleted or updated, including being marked Completed. "
		"Kratium does not have a separate calendar archive operation."
	),
	"actions": (
		"Actions form a hierarchy through parent_action and ancestor. "
		"Actions may also represent todos, events, routines, goals, groups, and milestones."
	),
	"permissions": (
		"Clarification resolves meaning and implementation scope. "
		"Permission checks, destructive-action confirmation, and execution approval belong to the execution bus."
	),
	"information_sources": (
		"System tools can read the current user, discover readable Kratium DocTypes and fields, "
		"query records, search records, read exact records, and count records. "
		"Web tools can search the public web and read public pages."
	),
}


def setup_logfire():
	logfire.configure(
		send_to_logfire=True,
		service_name="kratium-ai",
		environment=os.getenv("LOGFIRE_ENVIRONMENT", "development"),
		config_dir=APP_DIRECTORY,
		data_dir=LOGFIRE_DIRECTORY,
		console=logfire.ConsoleOptions(
			span_style="indented",
			include_timestamps=True,
			include_tags=True,
			verbose=True,
			min_log_level="debug",
			show_project_link=False,
		),
	)
	logfire.instrument_pydantic_ai(
		include_content=True,
		include_binary_content=False,
		version=1,
		event_mode="logs",
	)
	logfire.instrument_system_metrics()


setup_logfire()


def get_google_api_key():
	api_key = os.getenv("GOOGLE_API_KEY")

	if not api_key:
		try:
			import frappe

			api_key = frappe.conf.get("google_api_key")
		except Exception:
			pass

	if not api_key:
		raise RuntimeError("Set GOOGLE_API_KEY or google_api_key in the Frappe site config")

	return api_key


def create_ai_agent(output_type, instructions, model_name=CHEAP_MODEL, **agent_options):
	model = GeminiModel(
		model_name,
		provider=GoogleGLAProvider(api_key=get_google_api_key()),
	)

	return Agent(
		model,
		output_type=output_type,
		instructions=instructions,
		model_settings=MODEL_SETTINGS,
		**agent_options,
	)

# endregion 1. SETUP


# region 1. SCHEMAS
class Schema(BaseModel):
	model_config = ConfigDict(extra="forbid")


class OrchestrationInput(Schema):
	input: str = Field(min_length=1)
	source: str = Field(min_length=1)
	context: dict[str, Any] = Field(default_factory=dict)


class Evidence(Schema):
	source: Literal["input", "system", "web", "user", "agent"]
	reference: str
	fact: str


class InformationRequest(Schema):
	request_id: str = Field(default_factory=lambda: str(uuid4()))
	question: str = Field(min_length=1)
	reason: str = Field(min_length=1)
	desired_output: str = Field(min_length=1)
	source_scope: Literal["system", "web", "both"] = "system"
	context: dict[str, Any] = Field(default_factory=dict)


class InformationResult(Schema):
	request_id: str
	status: Literal["complete", "partial", "not_found"]
	answer: Any
	requested_output: str
	strategy: list[str] = Field(min_length=1)
	facts: list[Evidence]
	missing_information: list[str] = Field(default_factory=list)
	confidence: float = Field(ge=0, le=1)


class InformationAnswer(Schema):
	status: Literal["answered"] = "answered"
	results: list[InformationResult] = Field(min_length=1)


class SystemField(Schema):
	fieldname: str
	label: str | None = None
	fieldtype: str
	options: str | None = None
	required: bool = False
	read_only: bool = False


class DoctypeDescription(Schema):
	doctype: str
	module: str | None = None
	title_field: str | None = None
	is_tree: bool = False
	fields: list[SystemField]


class SystemRecordResult(Schema):
	doctype: str
	filters: dict[str, Any] = Field(default_factory=dict)
	records: list[dict[str, Any]]
	count: int


class WebSource(Schema):
	title: str
	url: str


class WebSearchResult(Schema):
	query: str
	status: Literal["complete", "unavailable"]
	answer: str = ""
	sources: list[WebSource] = Field(default_factory=list)
	error: str | None = None


class WebPageResult(Schema):
	url: str
	title: str
	content: str


class UserQuestion(Schema):
	question: str
	reason: str
	options: list[str] = Field(default_factory=list)


class UserClarification(Schema):
	status: Literal["needs_user"] = "needs_user"
	questions: list[UserQuestion] = Field(min_length=1)
	blocked_decisions: list[str] = Field(min_length=1)


class ProblemBreakdown(Schema):
	goal: str
	ambiguities: list[str] = Field(default_factory=list)
	assumptions: list[str] = Field(default_factory=list)
	information_needed: list[str] = Field(default_factory=list)


class ClarificationResult(Schema):
	problem: ProblemBreakdown
	evidence: list[Evidence]
	confidence: float = Field(ge=0, le=1)


class RouteOption(Schema):
	route_id: str
	description: str
	expected_outcome: str
	evidence: list[Evidence] = Field(min_length=1)
	risks: list[str] = Field(default_factory=list)
	confidence: float = Field(ge=0, le=1)


class Decision(Schema):
	decision_id: str
	question: str
	conclusion: str
	alternatives: list[str] = Field(default_factory=list)
	evidence: list[Evidence] = Field(min_length=1)
	confidence: float = Field(ge=0, le=1)


class RouteSelection(Schema):
	routes: list[RouteOption] = Field(min_length=1)
	chosen_route_id: str
	decisions: list[Decision] = Field(min_length=1)


class ActionDependency(Schema):
	action_id: str | None = None
	operation_id: str | None = None

	@model_validator(mode="after")
	def has_one_reference(self):
		if (self.action_id is None) == (self.operation_id is None):
			raise ValueError("Use either action_id or operation_id")
		return self


class ActionConstraint(Schema):
	action_id: str
	constraint: Literal["FS", "SS", "FF", "SF"]


class ActionChanges(Schema):
	action_name: str | None = None
	description: str | None = None
	start_date: datetime | None = None
	end_date: datetime | None = None
	estimated_hours: float | None = Field(default=None, ge=0)
	parent_action: str | None = None
	ancestor: str | None = None
	category: str | None = None
	status: Literal["Upcoming", "In Progress", "Completed"] | None = None
	is_group: bool | None = None
	todo: bool | None = None
	event: bool | None = None
	full_day: bool | None = None
	routine: bool | None = None
	completed: bool | None = None
	starred: bool | None = None
	milestone: bool | None = None
	milestone_action: str | None = None
	reminder: datetime | None = None
	reminder_type: Literal[
		"Once",
		"Until Completion",
		"Before Completion",
		"Snooze",
		"Follow Up",
	] | None = None
	reminder_interval: float | None = Field(default=None, ge=0)
	dependencies: list[ActionDependency] | None = None
	constraints: list[ActionConstraint] | None = None


class CreateAction(ActionChanges):
	operation: Literal["create"] = "create"
	operation_id: str
	decision_id: str
	action_name: str
	start_date: datetime
	end_date: datetime

	@model_validator(mode="after")
	def dates_are_valid(self):
		if self.end_date < self.start_date:
			raise ValueError("end_date cannot be before start_date")
		return self


class UpdateAction(Schema):
	operation: Literal["update"] = "update"
	operation_id: str
	decision_id: str
	action_id: str
	expected_modified: datetime
	changes: ActionChanges

	@model_validator(mode="after")
	def has_changes(self):
		if not self.changes.model_fields_set:
			raise ValueError("An update must contain at least one change")
		return self


class DeleteAction(Schema):
	operation: Literal["delete"] = "delete"
	operation_id: str
	decision_id: str
	action_id: str
	expected_modified: datetime


AtomicAction = Annotated[
	CreateAction | UpdateAction | DeleteAction,
	Field(discriminator="operation"),
]


class SuccessCriterion(Schema):
	description: str
	check: str
	expected_result: str
	check_after: datetime | None = None


class ActionDesign(Schema):
	decisions: list[Decision] = Field(min_length=1)
	actions: list[AtomicAction] = Field(min_length=1)
	success_criteria: list[SuccessCriterion] = Field(min_length=1)


class ExecutionPlan(Schema):
	status: Literal["ready"] = "ready"
	plan_id: str
	problem: ProblemBreakdown
	routes_considered: list[RouteOption] = Field(min_length=1)
	chosen_route_id: str
	decisions: list[Decision] = Field(min_length=1)
	actions: list[AtomicAction] = Field(min_length=1)
	success_criteria: list[SuccessCriterion] = Field(min_length=1)

	@model_validator(mode="after")
	def references_are_valid(self):
		route_ids = [route.route_id for route in self.routes_considered]
		decision_ids = [decision.decision_id for decision in self.decisions]
		operation_ids = [action.operation_id for action in self.actions]

		if self.chosen_route_id not in route_ids:
			raise ValueError("chosen_route_id is not in routes_considered")
		if len(route_ids) != len(set(route_ids)):
			raise ValueError("route_id values must be unique")
		if len(decision_ids) != len(set(decision_ids)):
			raise ValueError("decision_id values must be unique")
		if len(operation_ids) != len(set(operation_ids)):
			raise ValueError("operation_id values must be unique")
		if any(action.decision_id not in decision_ids for action in self.actions):
			raise ValueError("Every action must reference a decision")

		seen_operations = set()
		for action in self.actions:
			changes = action if isinstance(action, CreateAction) else getattr(action, "changes", None)
			for dependency in (changes.dependencies if changes else None) or []:
				if dependency.operation_id and dependency.operation_id not in seen_operations:
					raise ValueError("An action can only depend on an earlier operation")
			seen_operations.add(action.operation_id)
		return self


class OrchestrationPaused(Schema):
	status: Literal["paused"] = "paused"
	stage: Literal["route_selection", "implementation", "review", "monitoring"]
	required_tool: Literal["select_route", "design_implementation", "review_outcome"]
	reason: str


OrchestrationOutput = Annotated[
	UserClarification | InformationAnswer | ExecutionPlan | OrchestrationPaused,
	Field(discriminator="status"),
]


class ActionExecutionResult(Schema):
	operation_id: str
	status: Literal["completed", "failed", "skipped"]
	action_id: str | None = None
	before: dict[str, Any] | None = None
	after: dict[str, Any] | None = None
	error: str | None = None


class ExecutionReport(Schema):
	plan_id: str
	results: list[ActionExecutionResult]


class OutcomeReview(Schema):
	plan_id: str
	outcome: Literal["successful", "monitor", "repair", "revert"]
	evidence: list[Evidence]
	follow_up_plan: ExecutionPlan | None = None
	next_check: datetime | None = None

	@model_validator(mode="after")
	def follow_up_is_valid(self):
		if self.outcome in {"repair", "revert"} and self.follow_up_plan is None:
			raise ValueError("Repair and revert outcomes need a follow_up_plan")
		return self


class OrchestrationState(Schema):
	orchestration_id: str
	conversation_id: str | None = None
	message_history: list[dict[str, Any]] = Field(default_factory=list)
	stage: Literal[
		"clarification",
		"waiting_for_user",
		"route_selection",
		"implementation",
		"execution",
		"review",
		"monitoring",
		"complete",
	]
	input: OrchestrationInput
	clarification: ClarificationResult | None = None
	user_clarification: UserClarification | None = None
	information: list[InformationResult] = Field(default_factory=list)
	route_selection: RouteSelection | None = None
	action_design: ActionDesign | None = None
	execution_plan: ExecutionPlan | None = None
	execution_report: ExecutionReport | None = None
	outcome_review: OutcomeReview | None = None


class OrchestrationRunResult(Schema):
	output: OrchestrationOutput
	state: OrchestrationState

# endregion 1. SCHEMAS


# region 1. PROCESS


# region 2. ORCHESTRATOR
ORCHESTRATOR_INSTRUCTIONS = """
You control the orchestration process. Delegate each reasoning stage to its specialist tool.

Do not clarify the request, collect facts, choose a route, or design actions yourself.
Treat structured tool results as the context for the next stage.

If the user is asking only for information, call collect_information directly.
Split distinct questions into separate collect_information calls with the appropriate source_scope.
Each call's desired_output must describe only that call's question.
After every distinct question has a result, return InformationAnswer containing the exact results
stored in state. Do not send a read-only information request through clarification or route selection.

At clarification or waiting_for_user, call clarify_request.
If it returns UserClarification, return that exact schema.
If it returns ClarificationResult, continue to route selection.

At route_selection, call select_route when it is available.
At implementation, call design_implementation when it is available.
At review or monitoring, call review_outcome when it is available.

If the required specialist tool is not available, return OrchestrationPaused.
Only return ExecutionPlan after clarification, route selection, and action design exist in state.
"""

CLARIFICATION_INSTRUCTIONS = """
Clarify the user's intended outcome without choosing a route or designing actions.

Use the supplied system context before deciding that information is missing.
Call collect_information when the answer may exist in Kratium.

Identify ambiguities that could materially change what records are affected, the timeframe,
the intended outcome, or another implementation detail.

Do not ask whether the user confirms, approves, or grants permission for a destructive or bulk action.
Those controls belong to the execution bus.

Return ClarificationResult when the goal is sufficiently specific to select a route.
Return UserClarification when a material decision still needs the user.
Ask the fewest questions possible and combine related missing details into one useful question.
Never ask the user for information that the system can answer.
"""

INFORMATION_INSTRUCTIONS = """
Answer the supplied InformationRequest by investigating available sources.

First decide the smallest useful investigation strategy. Then call utility tools, inspect their
results, follow relevant relationships, and continue until the requested answer is supported or
the available sources are exhausted.

Use system tools for Kratium facts. Use web search only when source_scope permits it and current
external information is genuinely required. Never mutate system data.

The request context describes the system capabilities available to you. For questions about the
person using Kratium, call get_current_user. For web questions, search first and then read the
most relevant result pages when snippets alone do not support the answer.

Do not guess DocType fields or record identifiers. Discover the available DocTypes and fields when
needed. Prefer focused queries, but widen or follow parent records when the first result is
insufficient. Distinguish facts returned by tools from your own inference.

Return answer in the exact form described by desired_output. Include the investigation strategy,
the evidence supporting the answer, anything still missing, and a calibrated confidence score.
Use the exact request_id and desired_output supplied in the request.
"""

_orchestrator_agents = {}
_clarification_agent = None
_information_agents = {}


def get_clarification_agent():
	global _clarification_agent

	if _clarification_agent is None:
		_clarification_agent = create_ai_agent(
			ClarificationResult | UserClarification,
			CLARIFICATION_INSTRUCTIONS,
			deps_type=OrchestrationState,
			tools=[collect_information],
			name="clarification_agent",
			retries=2,
		)

	return _clarification_agent


def get_information_agent(source_scope="system"):
	if source_scope not in _information_agents:
		system_tools = [
			get_current_user,
			list_system_doctypes,
			describe_doctype,
			query_system_records,
			search_system_records,
			get_system_record,
			count_system_records,
		]
		tools = {
			"system": system_tools,
			"web": [search_web, read_web_page],
			"both": [*system_tools, search_web, read_web_page],
		}[source_scope]

		agent = create_ai_agent(
			InformationResult,
			INFORMATION_INSTRUCTIONS,
			deps_type=InformationRequest,
			tools=tools,
			name=f"information_agent_{source_scope}",
			retries=3,
		)

		@agent.output_validator
		def validate_information_result(ctx, output):
			if output.request_id != ctx.deps.request_id:
				raise ModelRetry("Use the request_id from the InformationRequest")
			if output.requested_output != ctx.deps.desired_output:
				raise ModelRetry("Copy desired_output exactly into requested_output")
			if output.status == "complete" and output.missing_information:
				raise ModelRetry("A complete result cannot contain missing information")
			if isinstance(output.answer, str):
				try:
					output.answer = json.loads(output.answer)
				except json.JSONDecodeError:
					pass
			return output

		_information_agents[source_scope] = agent

	return _information_agents[source_scope]


def get_orchestrator_agent(information_only=False):
	if information_only not in _orchestrator_agents:
		tools = [Tool(collect_information, sequential=True)]
		if not information_only:
			tools.insert(0, clarify_request)

		agent = create_ai_agent(
			OrchestrationOutput,
			ORCHESTRATOR_INSTRUCTIONS,
			deps_type=OrchestrationState,
			tools=tools,
			name="orchestrator_agent",
			retries=2,
		)

		@agent.output_validator
		def validate_orchestration_output(ctx, output):
			state = ctx.deps

			if isinstance(output, UserClarification):
				if state.stage != "waiting_for_user" or output != state.user_clarification:
					raise ModelRetry("Return the exact UserClarification produced by clarify_request")

			if isinstance(output, InformationAnswer):
				if not state.information:
					raise ModelRetry("Call collect_information before returning InformationAnswer")
				output = InformationAnswer(results=state.information)
				state.stage = "complete"

			if isinstance(output, OrchestrationPaused):
				required_tools = {
					"route_selection": "select_route",
					"implementation": "design_implementation",
					"review": "review_outcome",
					"monitoring": "review_outcome",
				}
				required_tool = required_tools.get(state.stage)
				if output.stage != state.stage or output.required_tool != required_tool:
					raise ModelRetry("Pause at the current stage and name its required specialist tool")

			if isinstance(output, ExecutionPlan):
				if not state.clarification or not state.route_selection or not state.action_design:
					raise ModelRetry("The specialist stages must finish before creating an ExecutionPlan")
				state.execution_plan = output
				state.stage = "execution"

			return output

		_orchestrator_agents[information_only] = agent

	return _orchestrator_agents[information_only]


def is_information_only(final_input):
	text = final_input.lower()
	information_markers = (
		"what ",
		"who ",
		"when ",
		"where ",
		"how ",
		"which ",
		"list ",
		"show ",
		"tell me",
		"find ",
		"weather ",
	)
	action_markers = (
		"create ",
		"add ",
		"delete ",
		"remove ",
		"clear ",
		"update ",
		"change ",
		"move ",
		"schedule ",
		"reschedule ",
		"allocate ",
		"set ",
		"mark ",
		"cancel ",
		"complete ",
		"remind ",
	)
	return (
		"?" in text or any(marker in text for marker in information_markers)
	) and not any(marker in text for marker in action_markers)


def start_orchestration(final_input):
	if isinstance(final_input, str):
		final_input = OrchestrationInput(input=final_input, source="direct")
	else:
		final_input = OrchestrationInput.model_validate(final_input)

	state = OrchestrationState(
		orchestration_id=str(uuid4()),
		stage="clarification",
		input=final_input,
	)
	return run_orchestrator(state)


def run_orchestrator(state, new_information=None):
	state = OrchestrationState.model_validate(state)
	message_history = (
		ModelMessagesTypeAdapter.validate_python(state.message_history)
		if state.message_history
		else None
	)

	prompt = f"Continue this orchestration:\n{state.model_dump_json(exclude={'message_history'})}"
	if new_information is not None:
		prompt += f"\nNew information:\n{to_jsonable_python(new_information)}"

	try:
		result = get_orchestrator_agent(
			information_only=is_information_only(state.input.input),
		).run_sync(
			prompt,
			deps=state,
			message_history=message_history,
			conversation_id=state.conversation_id or state.orchestration_id,
			usage_limits=USAGE_LIMITS,
		)
	finally:
		logfire.force_flush(timeout_millis=5000)

	state.message_history = to_jsonable_python(result.all_messages())
	state.conversation_id = result.conversation_id

	return OrchestrationRunResult(output=result.output, state=state)


def resume_orchestration(state, new_information):
	state = OrchestrationState.model_validate(state)

	if isinstance(new_information, ExecutionReport):
		state.execution_report = new_information
		state.stage = "review"

	return run_orchestrator(state, new_information)

# endregion 2. ORCHESTRATOR


# region 2. HANDOFFS
def request_user_clarification(state, clarification):
	# Pauses the stream and resumes it when the user's answer is available.
	pass


def compile_execution_plan(state):
	# Validates and assembles the final schema sent to the execution bus.
	pass


def handoff_to_execution_bus(state, plan):
	# The execution report returns to resume_orchestration.
	pass


def schedule_outcome_review(state, review):
	# A future monitoring result returns to resume_orchestration.
	pass

# endregion 2. HANDOFFS


# endregion 1. PROCESS

# endregion ORCHESTRATION


# =============================================================================
# region EXECUTION BUS
# =============================================================================


# region 1. PROCESS
def execute_plan(plan):
	# Prepares the plan, waits for approval when required, then executes in order.
	pass


def prepare_execution(plan):
	# Checks permissions, references, stale records, ordering, and approval level.
	pass


def request_execution_approval(plan):
	# Bulk or high-risk plans cannot continue without explicit user approval.
	pass


def execute_atomic_action(action):
	# Applies exactly one create, update, or delete operation.
	pass


def build_execution_report(plan, results):
	# Returns every result and before/after state to the orchestrator.
	pass


def rollback_execution(results):
	# Restores completed operations when the execution transaction cannot finish.
	pass

# endregion 1. PROCESS


# endregion EXECUTION BUS


# =============================================================================
# region TOOLS
# =============================================================================


# region 1. STAGE TOOLS
async def clarify_request(ctx: RunContext[OrchestrationState]):
	"""Return clarified intent or the questions that block clarification."""
	state = ctx.deps
	if state.stage not in {"clarification", "waiting_for_user"}:
		raise ModelRetry("clarify_request is only available during clarification")

	prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		f"\n\nCurrent orchestration update:\n{ctx.prompt}"
	)
	result = await get_clarification_agent().run(
		prompt,
		deps=state,
		usage=ctx.usage,
		usage_limits=USAGE_LIMITS,
	)

	if isinstance(result.output, UserClarification):
		state.user_clarification = result.output
		state.stage = "waiting_for_user"
	else:
		state.clarification = result.output
		state.user_clarification = None
		state.stage = "route_selection"

	return result.output


async def collect_information(
	ctx: RunContext[OrchestrationState],
	question: str,
	reason: str,
	desired_output: str,
	source_scope: Literal["system", "web", "both"] = "system",
	context: dict[str, Any] | None = None,
):
	"""Investigate a question and return the answer in the requested form."""
	system_terms = {
		"kratium",
		"doctype",
		"action",
		"calendar",
		"reminder",
		"meal",
		"grocery",
		"storage location",
	}
	if source_scope == "web" and any(term in question.lower() for term in system_terms):
		source_scope = "system"

	request = InformationRequest(
		question=question,
		reason=reason,
		desired_output=desired_output,
		source_scope=source_scope,
		context={
			"system_context": SYSTEM_CONTEXT,
			"readable_doctypes": sorted(AI_READABLE_DOCTYPES),
			"available_tools": {
				"system": [
					"get_current_user",
					"list_system_doctypes",
					"describe_doctype",
					"query_system_records",
					"search_system_records",
					"get_system_record",
					"count_system_records",
				],
				"web": ["search_web", "read_web_page"],
			},
			"current_datetime": datetime.now().astimezone().isoformat(),
			**(context or {}),
		},
	)
	result = await get_information_agent(source_scope).run(
		request.model_dump_json(),
		deps=request,
		usage=ctx.usage,
		usage_limits=USAGE_LIMITS,
	)
	ctx.deps.information.append(result.output)
	return result.output


def select_route(state):
	# Returns the considered routes and selected route.
	pass


def design_implementation(state):
	# Returns decisions, atomic actions, and success checks.
	pass


def review_outcome(state):
	# Returns whether to complete, monitor, repair, or revert.
	pass

# endregion 1. STAGE TOOLS


# region 1. UTILITY TOOLS
STANDARD_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
}


def _get_readable_meta(doctype):
	import frappe

	if doctype not in AI_READABLE_DOCTYPES:
		raise ValueError(f"{doctype} is not available to AI read tools")
	if not frappe.db.exists("DocType", doctype):
		raise ValueError(f"Unknown DocType: {doctype}")
	return frappe.get_meta(doctype)


def _validate_fields(meta, fields):
	available_fields = STANDARD_FIELDS | {field.fieldname for field in meta.fields}
	selected_fields = fields or ["name"]
	invalid_fields = set(selected_fields) - available_fields
	if invalid_fields:
		raise ValueError(f"Unknown fields for {meta.name}: {sorted(invalid_fields)}")
	return selected_fields


def _validate_filters(meta, filters):
	filters = filters or {}
	_validate_fields(meta, list(filters))
	return filters


def _validate_order_by(meta, order_by):
	if not order_by:
		return None

	parts = order_by.split()
	if len(parts) > 2 or (len(parts) == 2 and parts[1].lower() not in {"asc", "desc"}):
		raise ValueError("order_by must contain one field and an optional asc or desc")
	_validate_fields(meta, [parts[0]])
	return order_by


def _system_source_allowed(ctx):
	if ctx.deps.source_scope == "web":
		raise ModelRetry("This request only permits web sources")


def _json_safe(value):
	return json.loads(json.dumps(value, default=str))


def get_current_user(ctx: RunContext[InformationRequest]):
	"""Return the authenticated Kratium user's identity."""
	import frappe

	_system_source_allowed(ctx)
	user_id = getattr(frappe.local, "jwt_user", None) or frappe.session.user
	user = frappe.get_doc("User", user_id)
	user.check_permission("read")
	return {
		"user_id": user.name,
		"full_name": user.full_name,
		"first_name": user.first_name,
		"last_name": user.last_name,
		"username": user.username,
		"email": user.email,
	}


def list_system_doctypes(ctx: RunContext[InformationRequest]):
	"""List the Kratium DocTypes available to the information agent."""
	_system_source_allowed(ctx)
	doctypes = []
	for doctype in sorted(AI_READABLE_DOCTYPES):
		meta = _get_readable_meta(doctype)
		doctypes.append({
			"name": doctype,
			"module": meta.module,
			"is_tree": bool(meta.is_tree),
		})
	return doctypes


def describe_doctype(ctx: RunContext[InformationRequest], doctype: str):
	"""Return readable fields and relationships for one Kratium DocType."""
	_system_source_allowed(ctx)
	meta = _get_readable_meta(doctype)
	return DoctypeDescription(
		doctype=doctype,
		module=meta.module,
		title_field=meta.title_field,
		is_tree=bool(meta.is_tree),
		fields=[
			SystemField(
				fieldname=field.fieldname,
				label=field.label,
				fieldtype=field.fieldtype,
				options=field.options,
				required=bool(field.reqd),
				read_only=bool(field.read_only),
			)
			for field in meta.fields
			if field.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
		],
	)


def query_system_records(
	ctx: RunContext[InformationRequest],
	doctype: str,
	filters: dict[str, Any] | None = None,
	fields: list[str] | None = None,
	order_by: str | None = None,
	limit: int = 20,
	offset: int = 0,
):
	"""Query records with Frappe permissions applied."""
	import frappe

	_system_source_allowed(ctx)
	meta = _get_readable_meta(doctype)
	filters = _validate_filters(meta, filters)
	fields = _validate_fields(meta, fields)
	order_by = _validate_order_by(meta, order_by)
	limit = max(1, min(limit, 100))
	offset = max(0, offset)

	records = frappe.get_list(
		doctype,
		filters=filters,
		fields=fields,
		order_by=order_by,
		limit_start=offset,
		limit_page_length=limit,
	)
	return SystemRecordResult(
		doctype=doctype,
		filters=filters,
		records=_json_safe(records),
		count=len(records),
	)


def search_system_records(
	ctx: RunContext[InformationRequest],
	doctype: str,
	query: str,
	search_fields: list[str] | None = None,
	filters: dict[str, Any] | None = None,
	fields: list[str] | None = None,
	limit: int = 20,
):
	"""Search readable text fields and return matching records."""
	import frappe

	_system_source_allowed(ctx)
	meta = _get_readable_meta(doctype)
	filters = _validate_filters(meta, filters)
	fields = _validate_fields(meta, fields)
	if not search_fields:
		search_fields = [
			field.fieldname
			for field in meta.fields
			if field.fieldtype in {"Data", "Small Text", "Text", "Text Editor", "Link"}
		]
	search_fields = _validate_fields(meta, search_fields)
	limit = max(1, min(limit, 100))

	records = frappe.get_list(
		doctype,
		filters=filters,
		or_filters=[
			[doctype, fieldname, "like", f"%{query}%"]
			for fieldname in search_fields
		],
		fields=fields,
		limit_page_length=limit,
	)
	return SystemRecordResult(
		doctype=doctype,
		filters=filters,
		records=_json_safe(records),
		count=len(records),
	)


def get_system_record(
	ctx: RunContext[InformationRequest],
	doctype: str,
	name: str,
	fields: list[str] | None = None,
):
	"""Read one exact record with Frappe permissions applied."""
	import frappe

	_system_source_allowed(ctx)
	meta = _get_readable_meta(doctype)
	fields = _validate_fields(meta, fields)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	data = doc.as_dict()
	return {
		"doctype": doctype,
		"name": name,
		"record": _json_safe({field: data.get(field) for field in fields}),
	}


def count_system_records(
	ctx: RunContext[InformationRequest],
	doctype: str,
	filters: dict[str, Any] | None = None,
):
	"""Count records with Frappe permissions applied."""
	import frappe

	_system_source_allowed(ctx)
	meta = _get_readable_meta(doctype)
	filters = _validate_filters(meta, filters)
	result = frappe.get_list(
		doctype,
		filters=filters,
		fields=[{"COUNT": "*", "as": "count"}],
		limit_page_length=1,
	)
	return {
		"doctype": doctype,
		"filters": filters,
		"count": result[0].get("count", 0) if result else 0,
	}


async def search_web(ctx: RunContext[InformationRequest], query: str):
	"""Search the public web and return current result pages."""
	if ctx.deps.source_scope == "system":
		raise ModelRetry("This request only permits Kratium system sources")

	with logfire.span("search web", query=query, request_id=ctx.deps.request_id):
		try:
			results = await asyncio.to_thread(
				lambda: list(DDGS().text(query, max_results=8))
			)
		except Exception as error:
			return WebSearchResult(
				query=query,
				status="unavailable",
				error=str(error),
			)

	if not results:
		return WebSearchResult(
			query=query,
			status="unavailable",
			error="No web results were returned",
		)

	return WebSearchResult(
		query=query,
		status="complete",
		answer="\n\n".join(
			f"{result.get('title', 'Untitled')}: {result.get('body', '')}"
			for result in results
		),
		sources=[
			WebSource(
				title=result.get("title") or result["href"],
				url=result["href"],
			)
			for result in results
			if result.get("href")
		],
	)


async def read_web_page(ctx: RunContext[InformationRequest], url: str):
	"""Read useful text from a public web page."""
	if ctx.deps.source_scope == "system":
		raise ModelRetry("This request only permits Kratium system sources")

	headers = {"User-Agent": "Mozilla/5.0 (compatible; Kratium/1.0)"}
	current_url = url

	async with httpx.AsyncClient(timeout=MODEL_SETTINGS["timeout"]) as client:
		for _ in range(5):
			await validate_public_url(current_url)
			response = await client.get(current_url, headers=headers, follow_redirects=False)
			if response.is_redirect:
				current_url = urljoin(current_url, response.headers["location"])
				continue
			response.raise_for_status()
			break
		else:
			raise ModelRetry("The page redirected too many times")

	content_type = response.headers.get("content-type", "")
	if "text/html" not in content_type and "text/plain" not in content_type:
		raise ModelRetry(f"Unsupported page content type: {content_type}")

	soup = BeautifulSoup(response.text, "html.parser")
	for element in soup(["script", "style", "noscript", "svg"]):
		element.decompose()
	title = soup.title.get_text(" ", strip=True) if soup.title else current_url
	content = "\n".join(
		line.strip()
		for line in soup.get_text("\n").splitlines()
		if line.strip()
	)
	return WebPageResult(
		url=current_url,
		title=title,
		content=content[:30_000],
	)


async def validate_public_url(url):
	parts = urlsplit(url)
	if parts.scheme not in {"http", "https"} or not parts.hostname:
		raise ModelRetry("Only public HTTP and HTTPS URLs can be read")

	loop = asyncio.get_running_loop()
	addresses = await loop.run_in_executor(
		None,
		lambda: socket.getaddrinfo(
			parts.hostname,
			parts.port or (443 if parts.scheme == "https" else 80),
			type=socket.SOCK_STREAM,
		),
	)
	for address in addresses:
		ip = ipaddress.ip_address(address[4][0])
		if not ip.is_global:
			raise ModelRetry("Private and local network addresses cannot be read")

# endregion 1. UTILITY TOOLS


# endregion TOOLS
