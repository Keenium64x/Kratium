import asyncio
import ipaddress
import json
import os
import re
import socket
import time as time_module
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urljoin, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import logfire
from bs4 import BeautifulSoup
from ddgs import DDGS
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent, ModelHTTPError, ModelMessagesTypeAdapter, ModelRetry, RunContext, Tool, UnexpectedModelBehavior, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
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

LOGFIRE_CONSOLE_VERBOSE = os.getenv("KRATIUM_AI_LOGFIRE_VERBOSE", "0") == "1"

INFORMATION_REQUIREMENT_STOPWORDS = {
	"a",
	"an",
	"and",
	"are",
	"as",
	"be",
	"by",
	"for",
	"from",
	"in",
	"into",
	"is",
	"it",
	"must",
	"of",
	"on",
	"or",
	"preserve",
	"required",
	"should",
	"that",
	"the",
	"this",
	"to",
	"using",
	"with",
}

MODEL_SETTINGS = GeminiModelSettings(
	temperature=0,
	max_tokens=8192,
	timeout=45,
)

USAGE_LIMITS = UsageLimits(
	request_limit=18,
	tool_calls_limit=40,
	total_tokens_limit=80_000,
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
		"Actions may also represent todos, events, routines, goals, groups, and milestones. "
		"Calendar questions should be answered from Action records where event is enabled."
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
	"execution_bus": (
		"The execution bus syncs approved atomic operations. Supported families are DocType create/update/delete, "
		"report run, dashboard refresh, scheduler run for allowed Kratium methods, notification preparation, "
		"and future external calls after allowlisting. Every mutating operation must pass security approval before sync."
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
			verbose=LOGFIRE_CONSOLE_VERBOSE,
			min_log_level="debug" if LOGFIRE_CONSOLE_VERBOSE else "warning",
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


def logfire_status():
	"""Return the AI observability settings currently used by Kratium."""
	return {
		"send_to_logfire": True,
		"console_verbose": LOGFIRE_CONSOLE_VERBOSE,
		"environment": os.getenv("LOGFIRE_ENVIRONMENT", "development"),
		"config_dir": str(APP_DIRECTORY),
		"data_dir": str(LOGFIRE_DIRECTORY),
		"project_url": "https://logfire-eu.pydantic.dev/keenium64x/kratium",
		"verbose_console_env": "KRATIUM_AI_LOGFIRE_VERBOSE=1",
	}


def network_status():
	"""Return DNS reachability for the external AI and observability endpoints."""
	checks = {}
	for host in ("generativelanguage.googleapis.com", "logfire-eu.pydantic.dev"):
		try:
			checks[host] = {
				"ok": True,
				"addresses": [item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)],
			}
		except socket.gaierror as error:
			checks[host] = {"ok": False, "error": str(error)}
	return checks


def _safe_logfire_attributes(**attributes):
	return {key: value for key, value in attributes.items() if value is not None}


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
	default: Any = None
	depends_on: str | None = None


class DoctypeDescription(Schema):
	doctype: str
	module: str | None = None
	title_field: str | None = None
	is_tree: bool = False
	fields: list[SystemField]


class SystemRecordResult(Schema):
	doctype: str
	filters: Any = Field(default_factory=dict)
	records: list[dict[str, Any]]
	count: int
	limit: int | None = None
	offset: int | None = None
	has_more: bool = False
	note: str | None = None


class DateRangeResult(Schema):
	label: str
	start: datetime
	end: datetime
	timezone: str | None = None


class DateTimeResult(Schema):
	label: str
	value: datetime
	timezone: str | None = None


class LinkField(Schema):
	fieldname: str
	label: str | None = None
	fieldtype: str
	options: str
	direction: Literal["outgoing", "incoming"]
	doctypes: list[str] = Field(default_factory=list)


class RelationshipMap(Schema):
	doctype: str
	outgoing_links: list[LinkField]
	incoming_links: list[LinkField]


class OperationFieldPlan(Schema):
	doctype: str
	operation_type: Literal["doctype.create", "doctype.update"]
	required_fields: list[str]
	relevant_fields: list[str]
	avoid_fields: list[str]
	field_types: dict[str, str] = Field(default_factory=dict)
	select_options: dict[str, list[str]] = Field(default_factory=dict)
	field_guidance: dict[str, str]
	system_notes: list[str] = Field(default_factory=list)


class ActionLookupResult(Schema):
	filters: Any = Field(default_factory=dict)
	records: list[dict[str, Any]]
	count: int
	limit: int
	has_more: bool = False
	note: str | None = None


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


class UserClarificationAnswer(Schema):
	answered_questions: list[dict[str, Any]] = Field(min_length=1)
	freeform_answer: str | None = None


class DesignQuestion(Schema):
	question_id: str
	phase: Literal["scope", "extent", "structure", "assumptions", "specifics"]
	question: str
	reason: str
	options: list[str] = Field(default_factory=list)
	default_assumption: str | None = None
	required: bool = True


class DesignAssumption(Schema):
	assumption_id: str
	category: Literal["scope", "structure", "content", "naming", "timing", "fields", "doctype", "security", "other"]
	statement: str
	reason: str
	confidence: float = Field(ge=0, le=1)
	ask_if_below: float = Field(default=0.65, ge=0, le=1)
	impact: Literal["low", "medium", "high", "critical"] = "medium"


class DesignUnknown(Schema):
	unknown_id: str
	category: Literal["scope", "structure", "content", "naming", "timing", "fields", "doctype", "other"]
	question: str
	reason: str
	impact: Literal["low", "medium", "high", "critical"]
	default_assumption: str | None = None
	options: list[str] = Field(default_factory=list)
	fieldname: str | None = None
	ask: bool = False


class DesignMapDimensionReview(Schema):
	dimension: Literal["scope", "scale", "structure", "timing", "naming", "content", "fields", "relationships", "assumptions", "security_separation", "other"]
	status: Literal["resolved", "assumed", "delegated", "needs_user"]
	impact: Literal["low", "medium", "high", "critical"]
	reason: str
	next_gap: str | None = None


class DesignFieldIntent(Schema):
	doctype: str
	fieldname: str
	label: str | None = None
	value_strategy: Literal["user_provided", "inferred", "assumed", "ask", "skip"] = "skip"
	value: Any = None
	reason: str = ""
	confidence: float = Field(default=0.5, ge=0, le=1)


class DesignImplementationRequirement(Schema):
	requirement_id: str
	category: Literal["scope", "structure", "content", "naming", "timing", "fields", "doctype", "relationship", "template", "other"]
	description: str
	source: Literal["prompt", "answer", "information_map", "doctype", "inferred"] = "information_map"
	must_preserve: bool = True
	evidence: list[str] = Field(default_factory=list)
	blueprint_hint: str = ""
	validation_terms: list[str] = Field(default_factory=list)


class DesignInformationMap(Schema):
	goal: str
	domain: Literal["workout", "study", "generic"]
	scope_type: Literal["simple_action", "structured_plan", "large_regime", "generic_structured_plan"]
	target_doctype: str = "Action"
	question_budget: dict[str, Any] = Field(default_factory=dict)
	doctype_strategy: dict[str, Any] = Field(default_factory=dict)
	scale_model: dict[str, Any] = Field(default_factory=dict)
	structure_model: dict[str, Any] = Field(default_factory=dict)
	content_model: dict[str, Any] = Field(default_factory=dict)
	time_model: dict[str, Any] = Field(default_factory=dict)
	naming_model: dict[str, Any] = Field(default_factory=dict)
	field_intents: list[DesignFieldIntent] = Field(default_factory=list)
	implementation_requirements: list[DesignImplementationRequirement] = Field(default_factory=list)
	assumptions: list[DesignAssumption] = Field(default_factory=list)
	unknowns: list[DesignUnknown] = Field(default_factory=list)
	readiness: Literal["ready", "needs_question"] = "ready"
	readiness_reason: str = ""


class DesignQuestionPlan(Schema):
	plan_id: str = Field(default_factory=lambda: str(uuid4()))
	scope_type: Literal["simple_action", "structured_plan", "large_regime", "generic_structured_plan"]
	domain: Literal["workout", "study", "generic"]
	likely_action_count_range: tuple[int, int]
	questions: list[DesignQuestion] = Field(default_factory=list)
	inferred_answers: list[dict[str, Any]] = Field(default_factory=list)
	system_assumptions: list[str] = Field(default_factory=list)
	information_map: DesignInformationMap | None = None


class DesignQuestionPlannerDecision(Schema):
	status: Literal["ready", "ask"]
	reasoning_summary: str
	complexity_assessment: str
	estimated_total_questions: int = Field(ge=0, le=30)
	dimension_reviews: list[DesignMapDimensionReview] = Field(default_factory=list)
	ready_blockers: list[str] = Field(default_factory=list)
	question: DesignQuestion | None = None
	assumptions_to_make: list[DesignAssumption] = Field(default_factory=list)
	map_gaps_resolved_by_assumption: list[str] = Field(default_factory=list)

	@model_validator(mode="after")
	def question_matches_status(self):
		if self.status == "ask" and self.question is None:
			raise ValueError("status='ask' requires question")
		if self.status == "ready" and self.question is not None:
			raise ValueError("status='ready' must not include question")
		if self.status == "ready" and self.ready_blockers:
			raise ValueError("status='ready' cannot include ready_blockers")
		if self.status == "ready" and not self.dimension_reviews:
			raise ValueError("status='ready' requires dimension_reviews proving map completeness")
		if self.status == "ready" and any(review.status == "needs_user" and review.impact in {"high", "critical"} for review in self.dimension_reviews):
			raise ValueError("status='ready' cannot leave high-impact dimensions needing the user")
		return self


class ActionBlueprintItem(Schema):
	operation_id: str
	action_name: str
	description: str
	start_date: datetime
	end_date: datetime
	is_group: bool = False
	todo: bool = True
	event: bool = False
	parent_operation_id: str | None = None
	status: str = "Upcoming"


class ActionBlueprintTemplate(Schema):
	template_id: str
	name_pattern: str
	description_pattern: str
	count: int = Field(ge=1, le=500)
	parent_group_id: str | None = None
	variables: dict[str, list[str]] = Field(default_factory=dict)
	duration_minutes: int = Field(default=60, ge=1, le=1440)
	todo: bool = True
	event: bool = False


class ActionBlueprintGroup(Schema):
	group_id: str
	name: str
	description: str
	parent_group_id: str | None = None
	estimated_days: int = Field(default=1, ge=1, le=365)


class ActionImplementationBlueprint(Schema):
	domain: Literal["study", "workout", "generic"]
	target_action_count: int = Field(ge=1, le=500)
	title: str
	groups: list[ActionBlueprintGroup] = Field(default_factory=list)
	templates: list[ActionBlueprintTemplate] = Field(default_factory=list)
	assumptions: list[str] = Field(default_factory=list)
	implementation_notes: list[str] = Field(default_factory=list)

	@model_validator(mode="after")
	def blueprint_has_enough_action_capacity(self):
		group_count = len(self.groups) + 1
		template_count = sum(template.count for template in self.templates)
		if group_count + template_count < self.target_action_count:
			raise ValueError("Blueprint templates must have enough count capacity to reach target_action_count")
		return self


class ActionPlanBlueprint(Schema):
	blueprint_id: str = Field(default_factory=lambda: str(uuid4()))
	domain: Literal["study", "workout", "generic"]
	target_action_count: int
	items: list[ActionBlueprintItem] = Field(min_length=1)
	assumptions: list[str] = Field(default_factory=list)
	source: str = "deterministic_blueprint"


class ProblemBreakdown(Schema):
	goal: str
	ambiguities: list[str] = Field(default_factory=list)
	assumptions: list[str] = Field(default_factory=list)
	information_needed: list[str] = Field(default_factory=list)


class ClarificationResult(Schema):
	problem: ProblemBreakdown
	evidence: list[Evidence]
	confidence: float = Field(ge=0, le=1)


class AssumptionDecision(Schema):
	question: str
	assumption: str
	reason: str
	confidence: float = Field(ge=0, le=1)
	action: Literal["use_assumption", "notify_user", "ask_user"]
	evidence: list[Evidence] = Field(min_length=1)


class AssumptionNotification(Schema):
	notification_id: str = Field(default_factory=lambda: str(uuid4()))
	channel: Literal["smartwatch"] = "smartwatch"
	status: Literal["pending", "confirmed", "challenged"] = "pending"
	message: str
	assumption: str
	question: str
	confidence: float = Field(ge=0, le=1)
	options: list[str] = Field(default_factory=lambda: ["Confirm", "Challenge"])


class AssumptionReview(Schema):
	decisions: list[AssumptionDecision]
	clarified_goal: str
	remaining_questions: list[UserQuestion] = Field(default_factory=list)
	blocked_decisions: list[str] = Field(default_factory=list)
	confidence: float = Field(ge=0, le=1)


class RouteOption(Schema):
	route_id: str
	outcome_type: Literal[
		"create",
		"update",
		"delete",
		"reschedule",
		"classify",
		"read",
		"plan",
		"monitor",
		"ask_user",
	]
	description: str
	expected_outcome: str
	system_objects: list[str] = Field(default_factory=list)
	evidence: list[Evidence] = Field(min_length=1)
	missing_information: list[str] = Field(default_factory=list)
	reversibility: Literal["high", "medium", "low"] = "medium"
	risks: list[str] = Field(default_factory=list)
	confidence: float = Field(ge=0, le=1)
	score: float = Field(ge=0, le=1)


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


class OperationDependency(Schema):
	target: Literal["record", "operation"]
	scope: Literal["doctype", "report", "dashboard", "scheduler", "notification", "external", "system"] = "system"
	record_id: str | None = None
	operation_id: str | None = None

	@model_validator(mode="after")
	def has_one_reference(self):
		if self.target == "record" and not self.record_id:
			raise ValueError("Record dependencies need record_id")
		if self.target == "operation" and not self.operation_id:
			raise ValueError("Operation dependencies need operation_id")
		return self


class OperationBase(Schema):
	operation_id: str
	decision_id: str
	operation_type: Literal[
		"doctype.create",
		"doctype.update",
		"doctype.delete",
		"report.run",
		"dashboard.refresh",
		"scheduler.run",
		"notification.send",
		"external.call",
	]
	operation_family: Literal["doctype", "report", "dashboard", "scheduler", "notification", "external"]
	description: str
	dependencies: list[OperationDependency] = Field(default_factory=list)


class CreateRecord(OperationBase):
	operation_type: Literal["doctype.create"] = "doctype.create"
	operation_family: Literal["doctype"] = "doctype"
	doctype: str
	fields: dict[str, Any] = Field(min_length=1)


class UpdateRecord(OperationBase):
	operation_type: Literal["doctype.update"] = "doctype.update"
	operation_family: Literal["doctype"] = "doctype"
	doctype: str
	record_id: str
	expected_modified: datetime
	fields: dict[str, Any] = Field(min_length=1)


class DeleteRecord(OperationBase):
	operation_type: Literal["doctype.delete"] = "doctype.delete"
	operation_family: Literal["doctype"] = "doctype"
	doctype: str
	record_id: str | None = None
	expected_modified: datetime | None = None

	@model_validator(mode="after")
	def has_record_or_operation_dependency(self):
		if self.record_id:
			return self
		if any(dependency.target == "operation" for dependency in self.dependencies):
			return self
		raise ValueError("Delete operations need record_id or an operation dependency that creates the record")


class RunReport(OperationBase):
	operation_type: Literal["report.run"] = "report.run"
	operation_family: Literal["report"] = "report"
	report_name: str
	filters: dict[str, Any] = Field(default_factory=dict)


class RefreshDashboard(OperationBase):
	operation_type: Literal["dashboard.refresh"] = "dashboard.refresh"
	operation_family: Literal["dashboard"] = "dashboard"
	dashboard_name: str
	context: dict[str, Any] = Field(default_factory=dict)


class RunScheduler(OperationBase):
	operation_type: Literal["scheduler.run"] = "scheduler.run"
	operation_family: Literal["scheduler"] = "scheduler"
	scheduler_name: str
	parameters: dict[str, Any] = Field(default_factory=dict)


class SendNotification(OperationBase):
	operation_type: Literal["notification.send"] = "notification.send"
	operation_family: Literal["notification"] = "notification"
	channel: Literal["smartwatch", "email", "system"]
	message: str
	payload: dict[str, Any] = Field(default_factory=dict)


class ExternalCall(OperationBase):
	operation_type: Literal["external.call"] = "external.call"
	operation_family: Literal["external"] = "external"
	integration_name: str
	endpoint: str
	payload: dict[str, Any] = Field(default_factory=dict)


ExecutionOperation = Annotated[
	CreateRecord | UpdateRecord | DeleteRecord | RunReport | RefreshDashboard | RunScheduler | SendNotification | ExternalCall,
	Field(discriminator="operation_type"),
]


class SuccessCriterion(Schema):
	description: str
	check: str
	expected_result: str
	check_after: datetime | None = None


class ImplementationDesign(Schema):
	decisions: list[Decision] = Field(min_length=1)
	operations: list[ExecutionOperation] = Field(min_length=1)
	success_criteria: list[SuccessCriterion] = Field(min_length=1)


class ExecutionPlan(Schema):
	status: Literal["ready"] = "ready"
	plan_id: str
	problem: ProblemBreakdown
	routes_considered: list[RouteOption] = Field(min_length=1)
	chosen_route_id: str
	decisions: list[Decision] = Field(min_length=1)
	operations: list[ExecutionOperation] = Field(min_length=1)
	success_criteria: list[SuccessCriterion] = Field(min_length=1)

	@model_validator(mode="after")
	def references_are_valid(self):
		route_ids = [route.route_id for route in self.routes_considered]
		decision_ids = [decision.decision_id for decision in self.decisions]
		operation_ids = [operation.operation_id for operation in self.operations]

		if self.chosen_route_id not in route_ids:
			raise ValueError("chosen_route_id is not in routes_considered")
		if len(route_ids) != len(set(route_ids)):
			raise ValueError("route_id values must be unique")
		if len(decision_ids) != len(set(decision_ids)):
			raise ValueError("decision_id values must be unique")
		if len(operation_ids) != len(set(operation_ids)):
			raise ValueError("operation_id values must be unique")
		if any(operation.decision_id not in decision_ids for operation in self.operations):
			raise ValueError("Every operation must reference a decision")

		seen_operations = set()
		for operation in self.operations:
			for dependency in operation.dependencies:
				if dependency.operation_id and dependency.operation_id not in seen_operations:
					raise ValueError("An operation can only depend on an earlier operation")
			seen_operations.add(operation.operation_id)
		return self


class OrchestrationPaused(Schema):
	status: Literal["paused"] = "paused"
	stage: Literal["clarification", "route_selection", "implementation", "review", "monitoring"]
	required_tool: Literal["clarify_request", "select_route", "design_implementation", "review_outcome"]
	reason: str


OrchestrationOutput = Annotated[
	UserClarification | InformationAnswer | ExecutionPlan | OrchestrationPaused,
	Field(discriminator="status"),
]


class OperationExecutionResult(Schema):
	operation_id: str
	status: Literal["completed", "failed", "skipped"]
	doctype: str | None = None
	record_id: str | None = None
	before: dict[str, Any] | None = None
	after: dict[str, Any] | None = None
	error: str | None = None


class ExecutionReport(Schema):
	plan_id: str
	results: list[OperationExecutionResult]


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
	assumption_review: AssumptionReview | None = None
	assumption_notifications: list[AssumptionNotification] = Field(default_factory=list)
	information: list[InformationResult] = Field(default_factory=list)
	route_selection: RouteSelection | None = None
	action_design: ImplementationDesign | None = None
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
If select_route returns UserClarification, return that exact schema.
At implementation, call design_implementation when it is available.
At review or monitoring, call review_outcome when it is available.

If the required specialist tool is not available, return OrchestrationPaused.
When state.stage is implementation and design_implementation is unavailable, return OrchestrationPaused.
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

Default-to-progress rule:
- For broad creative create/plan requests, such as creating a workout routine, study plan, meal
  plan, or other generated structure, do not pause just because personalization details are
  missing. State reasonable default assumptions in ClarificationResult and proceed.
- Ask only when missing information changes existing records affected, legal/safety constraints,
  private credentials, irreversible external side effects, or the exact user objective cannot be
  inferred at all.
- User preferences like fitness goal, equipment, duration, style, or intensity are useful but not
  blockers when the user asks the AI to create a reasonable default plan.
"""

ASSUMPTION_REVIEW_INSTRUCTIONS = """
Review the questions that clarification wants to ask the user.

Your job is to decide whether each question really needs to be asked, or whether a reasonable
assumption can safely keep the workflow moving.

Use system context, current datetime, original input, clarification attempt, and collected facts.
Do not design routes or actions. Do not ask permission questions.

For each question, choose one action:
- use_assumption: confidence is high enough to proceed without asking.
- notify_user: confidence is medium; proceed with the assumption, but create a smartwatch-style
  notification payload so the user can confirm or challenge later.
- ask_user: confidence is too low or the wrong assumption could materially change records affected.

Guidance:
- If clarification asks for preference details for a broad creative create request, prefer
  use_assumption unless the missing detail changes existing records affected or creates a safety
  issue. The system can make a useful default plan and permissions handle mutation risk.
- If the user says "Saturday" and the current week has a clear upcoming Saturday, assuming the
  upcoming Saturday is usually reasonable.
- If the user says "clear my calendar" without a timeframe, do not assume all time; ask the user.
- If the assumption changes which existing records are updated or deleted, be more conservative.
- Permission, approval, and destructive-action confirmation belong to the execution bus, not here.

Return clarified_goal rewritten with the accepted assumptions included. Keep remaining_questions
only for decisions that still truly need user input.
"""

DESIGN_QUESTION_PLANNER_INSTRUCTIONS = """
You are the dynamic design-interview planner for Kratium.

Your job is not to follow a checklist. Your job is to read the user's original prompt, all prior
answers, and the current DesignInformationMap, then decide whether exactly one more question is
worth asking before implementation.

Core behavior:
- Build an internal information map covering scope, extent, structure, relationships, timing,
  naming, content detail, field strategy, assumptions, and implementation risk to the design.
- Estimate how many total questions the problem deserves based on complexity and the user's detail
  preference. Small/simple requests should need 0 questions. Broad system-design requests may need
  several, but only when each question materially changes the blueprint.
- If the user's answer already gives enough structure, do not ask generic follow-up questions like
  "how detailed should descriptions be". Make sensible assumptions and list them.
- If the user says "you decide", "figure it out", "make assumptions", or gives enough direction,
  proceed by strengthening assumptions instead of asking.
- Ask the fewest concise, high-leverage questions possible. Prefer one bundled question that
  resolves several connected assumptions over multiple template questions.
- The question must be specific to the actual build being discussed, not a reusable canned wording.
- Never ask security, approval, permission, or confirmation questions. Execution security handles
  final mutation risk.
- Do not ask about facts a system tool could discover. Use assumptions for creative preferences;
  leave system lookup to later implementation/information stages.

Return status="ready" when the map is sufficient for blueprint design. In that case include the
assumptions you are making, especially for loose naming, timing, tree structure, descriptions, and
field population.

Return status="ask" only when a missing decision would materially change the structure, count,
relationships, timing model, or meaning of the generated records. The question should be written
for the current prompt and prior answers.
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

For Action, calendar, hierarchy, category, or date-range questions, prefer the dedicated Action
and date helper tools before falling back to generic record queries.

Return answer in the exact form described by desired_output. Include the investigation strategy,
the evidence supporting the answer, anything still missing, and a calibrated confidence score.
Use the exact request_id and desired_output supplied in the request.
"""

ROUTE_SELECTION_INSTRUCTIONS = """
Select the most sensible route for achieving the clarified goal.

Use the clarification, collected information, system context, and current orchestration state.
Do not design atomic actions. Do not execute anything. Do not ask permission questions.

Route generation and selection are one stage for now. You must still do both parts explicitly:

1. Identify the outcome type: create, update, delete, reschedule, classify, read, plan, monitor,
or ask_user.
2. Generate candidate routes that are possible in the real Kratium system.
3. Call collect_information when a route decision depends on current Kratium records,
relationships, calendar state, categories, schedules, or other system facts that are not already
available.
4. Score each route from 0 to 1 using fit to goal, evidence, reversibility, risk, missing
information, and support from known Kratium objects.
5. Choose the highest-scoring route, or choose an ask_user route only if implementation details are
missing and cannot reasonably be inferred.

If you choose ask_user, make it a real route option. Its missing_information must name the exact
route-selection facts or decisions that block progress. Its evidence should explain why the system
cannot safely infer them. Do not invent an implementation route just to avoid asking the user.

Do not use route clarification as a security gate. Destructive, high-risk, broad, or random
mutation requests should still be routed if the implementation can produce concrete operations.
The execution bus security stage is responsible for permission prompts and final user approval.
If the user asks for a random choice, treat that as permission for the AI to choose a reasonable
candidate during implementation and document the choice in the route evidence/risks.

Known Kratium system objects and route patterns:
- Calendar events are Action records where event is enabled.
- Todos and scheduled work are also Action records.
- Actions can be hierarchical through parent_action and ancestor.
- Action Category can classify or group actions.
- Action Time Entry records execution/time tracking.
- Reminder Master records reminder behavior.
- Planning objects include Fact, Meal, Meal Plan, Grocery, Grocery Bin, Grocery Item, Grocery Stock
Entry, Grocery Stock Ledger Entry, Storage Location, UOM Conversion, and Unit of Measure.

For each candidate route, include outcome_type, system_objects, evidence, missing information,
risks, reversibility, confidence, and score. Consider practical alternatives when they could
materially change implementation. Every chosen_route_id must match one returned route_id.

The selected route should decide only the path. Atomic create/update/delete details belong to
design_implementation.

Coverage rule:
- Preserve every distinct requested intent. If one prompt asks to create something and also inspect,
  update, or delete existing records, the chosen route must cover all parts or ask the user.
- For compound mutation requests, use outcome_type="plan" and describe each sub-intent in the route.
- Never choose a create-only, update-only, or delete-only route when the request contains another
  explicit mutation intent.
"""

DESIGN_IMPLEMENTATION_INSTRUCTIONS = """
Convert the selected route into atomic execution-bus operations. Do not execute and do not ask
permission questions.

Return ImplementationDesign with decisions, operations, and success_criteria.

Operation contract:
- One operation = one atomic system action.
- DocType create/update/delete use operation_type doctype.create, doctype.update, or doctype.delete.
- Create/update fields must be valid writable fields for the target DocType.
- Update/delete must include record_id and expected_modified. Use collect_information to find
  candidates and choose a concrete record when the user explicitly asks for any/random/one matching
  record. Document why that record was chosen.
- Bulk requests become many atomic operations, not one bulk operation.

Use tools only when needed:
- Use collect_information for missing records, ids, modified timestamps, or system facts.
- Use plan_doctype_fields_for_operation before DocType create/update when field choices are not
  obvious from the route.

Field rules:
- Fill required fields and relevant useful optional fields.
- Do not include fields only because they exist.
- Avoid planning/tree/table/link fields unless route evidence supports them.
- For tree/hierarchy creation, create parent records before children. Child Link/parent fields may
  use the earlier parent operation_id; the execution bus resolves it to the created record name.
- For same-plan cross-record links, use a prior operation_id in the Link field and include/allow
  the operation dependency. Do not guess the final Frappe record name before sync.
- For Action calendar events normally fill action_name, description, start_date, end_date, event,
  todo=false, and status when useful.
- If the user asks for a random todo/name/time, choose a reasonable value and record that decision.
- If the user gives sparse information, fill as many relevant writable fields as make sense from
  the prompt, current context, DocType fields, and system conventions.

If deterministic implementation is still blocked, return UserClarification with the fewest needed
questions. Otherwise return operations that reference returned decision_id values.

Coverage rule:
- The operations must cover every explicit intent preserved in the selected route.
- If the request contains create + delete, include at least one create operation and either one
  delete operation per found record or a clear implementation decision proving no matching records
  exist.
- If records must be checked before delete/update, call collect_information and use exact record_id
  and expected_modified from the returned system facts.
- Never create placeholder, dummy, fake, or non-existent update/delete operations to represent
  "nothing to change". No matching records means no mutation operation for that sub-intent.
- If the user explicitly asks to create a temporary record and then delete it, create one
  doctype.create operation and one doctype.delete operation that depends on the create operation.
  In that case the delete operation should omit record_id and expected_modified and use an
  operation dependency pointing to the create operation.
"""

ACTION_BLUEPRINT_INSTRUCTIONS = """
Design an Action implementation blueprint, not execution operations.

Your job:
- Convert the user's clarified request into a scalable Action tree model.
- Use groups for hierarchy/containers and templates for repeated concrete Actions.
- Honor explicit counts such as 50, 100, or 300 Actions.
- If the prompt says fake/invented/random, choose appropriate concrete labels and record assumptions.
- Ask no security or permission questions.
- Output no doctype.create/delete/update operations.
- Create no temporary draft/delete steps unless the user explicitly asked for a temporary record.

The deterministic compiler expands your blueprint into atomic execution-bus operations.
Therefore group + template capacity must reach target_action_count.

For large systems, prefer compact repeated templates over listing hundreds of individual items.
For example, a 300-action study system should use subject/week/day groups and repeated study,
revision, practice, and test templates.

Use template variables for repeated dimensions instead of literal placeholders. Example:
- name_pattern: "{subject} Week {week}: {activity} {index}"
- variables: {"subject": ["Mathematics", "Physics"], "week": ["1", "2"], "activity": ["Concept Study", "Practice"]}

Every placeholder in name_pattern/description_pattern other than {index}, {n}, {number}, {total},
or {template_id} should have a matching variables entry. The compiler will cycle variables across
template instances.
"""

EXECUTION_SECURITY_INSTRUCTIONS = """
Review an execution plan and produce the security validations required before syncing.

You are the execution-bus security stage. Do not execute anything. Do not ask clarification
questions about the user intent. Your job is to decide what security approvals or blocks are needed
for the already-designed atomic operations.

Inputs include:
- the execution plan;
- deterministic operation-level security facts from the system;
- permission results;
- stale-record checks;
- record snapshots where relevant.

Return one ExecutionSecurityReview.

Rules:
- Every atomic operation must appear in operation_evaluations.
- If an operation has blocking_reasons, mark it blocked in the queue and do not include it in an
  approval group.
- Similar safe operations should be grouped into one approval prompt. For example, ten Action
  creates should normally be one create approval.
- Destructive operations need approval. Multiple normal deletes may be one delete approval group.
- Critical deletes, such as deleting a group, goal, parent action, or record with children, should
  be separated from ordinary deletes.
- The prompt text should explain what the approval covers, why the risk level was chosen, and
  whether explicit confirmation is required.
- Queue positions must start at 1 and preserve operation order.
- Every queued operation that appears in an approval prompt must reference that prompt's group_id
  in security_group_id.
- Every non-blocked operation with approval_required=true must appear in exactly one approval prompt.
- If nothing needs approval and nothing is blocked, status is ready_to_execute.
- If anything is blocked, status is blocked.
- Otherwise status is waiting_for_approval.
"""

_orchestrator_agents = {}
_clarification_agent = None
_assumption_review_agent = None
_design_question_planner_agent = None
_information_agents = {}
_route_selection_agent = None
_action_blueprint_agent = None
_action_design_agent = None
_execution_security_agent = None


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


def get_assumption_review_agent():
	global _assumption_review_agent

	if _assumption_review_agent is None:
		_assumption_review_agent = create_ai_agent(
			AssumptionReview,
			ASSUMPTION_REVIEW_INSTRUCTIONS,
			deps_type=OrchestrationState,
			tools=[collect_information, resolve_relative_datetime, resolve_date_range],
			name="assumption_review_agent",
			retries=2,
		)

		@_assumption_review_agent.output_validator
		def validate_assumption_review(ctx, output):
			if any(decision.action == "ask_user" for decision in output.decisions) and not output.remaining_questions:
				raise ModelRetry("ask_user assumption decisions must include remaining_questions")
			if any(decision.action != "ask_user" for decision in output.decisions) and not output.clarified_goal:
				raise ModelRetry("Accepted assumptions must be reflected in clarified_goal")
			return output

	return _assumption_review_agent


def get_design_question_planner_agent():
	global _design_question_planner_agent

	if _design_question_planner_agent is None:
		_design_question_planner_agent = create_ai_agent(
			DesignQuestionPlannerDecision,
			DESIGN_QUESTION_PLANNER_INSTRUCTIONS,
			name="design_question_planner_agent",
			retries=2,
		)

		@_design_question_planner_agent.output_validator
		def validate_design_question_planner(ctx, output):
			if output.status == "ask":
				question_text = (output.question.question if output.question else "").lower()
				if any(term in question_text for term in ("permission", "approve", "confirm", "security")):
					raise ModelRetry("Design interview must not ask permission/security questions.")
				if output.question and output.question.question_id in {"naming_rules", "timing_model", "content_detail_model"}:
					raise ModelRetry("Do not use old fixed question IDs. Create a prompt-specific question_id.")
				if output.question and not design_question_shapes_implementation_map(output.question):
					raise ModelRetry(
						"The design question is preference-only. Ask one concise question that shapes the implementation map: "
						"hierarchy, parent/child levels, templates versus generated instances, scale, timing/scheduling, naming, or assumptions."
					)
			return output

	return _design_question_planner_agent


def get_information_agent(source_scope="system"):
	if source_scope not in _information_agents:
		system_tools = [
			get_current_user,
			list_system_doctypes,
			describe_doctype,
			discover_doctype_relationships,
			resolve_date_range,
			resolve_relative_datetime,
			query_actions,
			get_action_context,
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


def get_route_selection_agent():
	global _route_selection_agent

	if _route_selection_agent is None:
		_route_selection_agent = create_ai_agent(
			RouteSelection,
			ROUTE_SELECTION_INSTRUCTIONS,
			deps_type=OrchestrationState,
			tools=[collect_information],
			name="route_selection_agent",
			retries=2,
		)

		@_route_selection_agent.output_validator
		def validate_route_selection(ctx, output):
			intent = detect_requested_intents(ctx.deps.input.input)
			route_ids = [route.route_id for route in output.routes]
			if output.chosen_route_id not in route_ids:
				raise ModelRetry("chosen_route_id must match one returned route_id")
			if len(route_ids) != len(set(route_ids)):
				raise ModelRetry("route_id values must be unique")
			if not output.decisions:
				raise ModelRetry("Route selection must include at least one decision")
			chosen_route = next(route for route in output.routes if route.route_id == output.chosen_route_id)
			if chosen_route.outcome_type == "ask_user":
				if not chosen_route.missing_information and not chosen_route.risks:
					raise ModelRetry("ask_user routes must explain what information blocks route selection")
				return output
			if len(intent["mutation_intents"]) > 1 and chosen_route.outcome_type != "plan":
				raise ModelRetry(
					"Compound mutation requests must choose a plan route that covers every explicit mutation intent"
				)
			missing_route_intents = missing_route_intents_for_choice(intent, chosen_route)
			if missing_route_intents:
				raise ModelRetry(f"Chosen route dropped requested intent(s): {missing_route_intents}")
			if chosen_route.outcome_type != "ask_user" and chosen_route.confidence < 0.65:
				raise ModelRetry("Low-confidence implementation routes should become an ask_user route")
			if chosen_route.outcome_type != "ask_user" and not chosen_route.system_objects:
				raise ModelRetry("Implementation routes must name the Kratium system objects they use")
			return output

	return _route_selection_agent


def get_action_blueprint_agent():
	global _action_blueprint_agent

	if _action_blueprint_agent is None:
		_action_blueprint_agent = create_ai_agent(
			ActionImplementationBlueprint | UserClarification,
			ACTION_BLUEPRINT_INSTRUCTIONS,
			deps_type=OrchestrationState,
			tools=[resolve_relative_datetime, resolve_date_range, describe_doctype_for_orchestration],
			name="action_blueprint_agent",
			retries=2,
		)

		@_action_blueprint_agent.output_validator
		def validate_action_blueprint(ctx, output):
			if isinstance(output, UserClarification):
				return output
			if output.target_action_count < 1 or output.target_action_count > 500:
				raise ModelRetry("target_action_count must be between 1 and 500")
			group_ids = [group.group_id for group in output.groups]
			template_ids = [template.template_id for template in output.templates]
			if len(group_ids) != len(set(group_ids)):
				raise ModelRetry("group_id values must be unique")
			if len(template_ids) != len(set(template_ids)):
				raise ModelRetry("template_id values must be unique")
			valid_group_ids = set(group_ids)
			for group in output.groups:
				if group.parent_group_id and group.parent_group_id not in valid_group_ids:
					raise ModelRetry("group parent_group_id must reference another group_id")
			for template in output.templates:
				if template.parent_group_id and template.parent_group_id not in valid_group_ids:
					raise ModelRetry("template parent_group_id must reference a group_id")
			capacity = 1 + len(output.groups) + sum(template.count for template in output.templates)
			if capacity < output.target_action_count:
				raise ModelRetry("Blueprint capacity is smaller than target_action_count")
			validate_blueprint_against_information_map(ctx, output)
			return output

	return _action_blueprint_agent


def validate_blueprint_against_information_map(ctx, blueprint):
	map_data = extract_information_map_from_blueprint_context(ctx)
	if not map_data:
		return
	requirements = map_data.get("implementation_requirements") or []
	missing_requirements = [
		requirement
		for requirement in requirements
		if requirement.get("must_preserve", True)
		and not blueprint_preserves_information_requirement(blueprint, requirement)
	]
	if missing_requirements:
		raise ModelRetry(
			"Blueprint did not preserve required information-map detail(s): "
			+ "; ".join(requirement.get("description", requirement.get("requirement_id", "unnamed requirement")) for requirement in missing_requirements[:3])
			+ ". Represent each requirement in groups, templates, variables, assumptions, or implementation_notes."
		)


def extract_information_map_from_blueprint_context(ctx):
	try:
		text = ctx.deps.input.input if ctx and ctx.deps and ctx.deps.input else ""
	except Exception:
		return None
	return extract_information_map_from_text(text)


def blueprint_preserves_information_requirement(blueprint, requirement):
	requirement = dict(requirement or {})
	terms = normalized_requirement_terms(requirement)
	if not terms:
		return True
	blueprint_text = normalized_blueprint_contract_text(blueprint)
	return any(term in blueprint_text for term in terms)


def normalized_requirement_terms(requirement):
	terms = []
	for key in ("validation_terms", "evidence"):
		for value in requirement.get(key) or []:
			terms.extend(extract_contract_terms(value))
	terms.extend(extract_contract_terms(requirement.get("description")))
	terms.extend(extract_contract_terms(requirement.get("blueprint_hint")))
	return list(dict.fromkeys(term for term in terms if len(term) > 2))


def normalized_blueprint_contract_text(blueprint):
	parts = [blueprint.title or ""]
	parts.extend(blueprint.assumptions or [])
	parts.extend(blueprint.implementation_notes or [])
	for group in blueprint.groups:
		parts.extend([group.group_id or "", group.name or "", group.description or ""])
	for template in blueprint.templates:
		parts.extend([template.template_id or "", template.name_pattern or "", template.description_pattern or ""])
		parts.extend((template.variables or {}).keys())
		for values in (template.variables or {}).values():
			parts.extend(values or [])
	return normalize_contract_text(" ".join(str(part) for part in parts if part is not None))


def extract_contract_terms(value):
	text = normalize_contract_text(value)
	if not text:
		return []
	phrases = [phrase.strip() for phrase in re.split(r"[,;:\n→]+", text) if phrase.strip()]
	terms = []
	for phrase in phrases:
		words = [word for word in re.findall(r"[a-z0-9_]+", phrase) if word not in INFORMATION_REQUIREMENT_STOPWORDS]
		if not words:
			continue
		terms.extend(words)
		if len(words) > 1:
			terms.append(" ".join(words[:4]))
	return terms


def normalize_contract_text(value):
	return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def get_action_design_agent():
	global _action_design_agent

	if _action_design_agent is None:
		_action_design_agent = create_ai_agent(
			ImplementationDesign | UserClarification,
			DESIGN_IMPLEMENTATION_INSTRUCTIONS,
			deps_type=OrchestrationState,
			tools=[
				collect_information,
				resolve_relative_datetime,
				resolve_date_range,
				plan_doctype_fields_for_operation,
				describe_doctype_for_orchestration,
				discover_doctype_relationships_for_orchestration,
			],
			name="action_design_agent",
			retries=2,
		)

		@_action_design_agent.output_validator
		def validate_action_design(ctx, output):
			if isinstance(output, UserClarification):
				return output

			state = ctx.deps
			intent = detect_requested_intents(state.input.input)
			implementation_decision_ids = [decision.decision_id for decision in output.decisions]
			available_decision_ids = {
				decision.decision_id for decision in state.route_selection.decisions
			} | set(implementation_decision_ids)
			operation_ids = [operation.operation_id for operation in output.operations]

			if len(implementation_decision_ids) != len(set(implementation_decision_ids)):
				raise ModelRetry("Implementation decision_id values must be unique")
			if len(operation_ids) != len(set(operation_ids)):
				raise ModelRetry("Atomic operation_id values must be unique")
			if any(operation.decision_id not in available_decision_ids for operation in output.operations):
				raise ModelRetry("Every operation must reference a route or implementation decision")

			chosen_route = next(
				route for route in state.route_selection.routes if route.route_id == state.route_selection.chosen_route_id
			)
			all_execution_operations = {
				"doctype.create",
				"doctype.update",
				"doctype.delete",
				"report.run",
				"dashboard.refresh",
				"scheduler.run",
				"notification.send",
				"external.call",
			}
			allowed_operations = {
				"create": {"doctype.create", "notification.send", "scheduler.run"},
				"update": {"doctype.update", "scheduler.run", "dashboard.refresh"},
				"delete": {"doctype.delete"},
				"reschedule": {"doctype.update", "scheduler.run"},
				"classify": {"doctype.update", "dashboard.refresh"},
				"plan": all_execution_operations,
				"monitor": {"doctype.create", "doctype.update", "scheduler.run", "notification.send"},
				"read": set(),
			}.get(chosen_route.outcome_type, set())
			operation_types = {operation.operation_type for operation in output.operations}
			if not operation_types <= allowed_operations:
				raise ModelRetry("Operations must match the selected route outcome type")
			missing_operation_intents = missing_operation_intents_for_design(intent, output)
			if missing_operation_intents:
				raise ModelRetry(f"Implementation dropped requested intent(s): {missing_operation_intents}")
			if not output.success_criteria:
				raise ModelRetry("Implementation design must include success criteria")

			for operation in output.operations:
				if isinstance(operation, (CreateRecord, UpdateRecord, DeleteRecord)) and operation.doctype not in AI_READABLE_DOCTYPES:
					raise ModelRetry("DocType operations must use known Kratium DocTypes")
				if isinstance(operation, UpdateRecord) and is_placeholder_record_id(operation.record_id):
					raise ModelRetry(
						"Update/delete operations must use real record_id values returned from system information. "
						"If no matching records exist, do not create a placeholder operation; record that no delete/update is needed in decisions."
					)
				if isinstance(operation, DeleteRecord) and operation.record_id and is_placeholder_record_id(operation.record_id):
					raise ModelRetry(
						"Delete operations must use real record_id values returned from system information, or depend on a prior create operation. "
						"Do not use placeholder record IDs."
					)
				if isinstance(operation, (CreateRecord, UpdateRecord)):
					try:
						validate_doctype_operation_fields(operation)
					except ValueError as exc:
						raise ModelRetry(str(exc)) from exc
				if isinstance(operation, UpdateRecord):
					operation.expected_modified = _coerce_datetime(operation.expected_modified)
				elif isinstance(operation, DeleteRecord) and operation.expected_modified:
					operation.expected_modified = _coerce_datetime(operation.expected_modified)

			return output

	return _action_design_agent


def get_execution_security_agent():
	global _execution_security_agent

	if _execution_security_agent is None:
		_execution_security_agent = create_ai_agent(
			ExecutionSecurityReview,
			EXECUTION_SECURITY_INSTRUCTIONS,
			deps_type=ExecutionPlan,
			tools=[],
			name="execution_security_agent",
			retries=2,
		)

		@_execution_security_agent.output_validator
		def validate_execution_security_review(ctx, output):
			plan = ctx.deps
			operation_ids = [operation.operation_id for operation in plan.operations]
			operation_by_id = {operation.operation_id: operation for operation in plan.operations}
			deterministic_evaluation_by_id = {
				evaluation.operation_id: evaluation
				for evaluation in [evaluate_operation_security(plan, operation) for operation in plan.operations]
			}
			evaluation_ids = [evaluation.operation_id for evaluation in output.operation_evaluations]
			queue_ids = [item.operation_id for item in output.queue]
			approval_operation_ids = [operation_id for prompt in output.approval_prompts for operation_id in prompt.operation_ids]
			approval_group_by_operation = {
				operation_id: prompt.group_id
				for prompt in output.approval_prompts
				for operation_id in prompt.operation_ids
			}
			valid_group_ids = {prompt.group_id for prompt in output.approval_prompts}

			if output.plan_id != plan.plan_id:
				raise ModelRetry("Security review plan_id must match the execution plan")
			if set(evaluation_ids) != set(operation_ids):
				raise ModelRetry("Every operation must have exactly one security evaluation")
			if len(evaluation_ids) != len(set(evaluation_ids)):
				raise ModelRetry("Security evaluations must not duplicate operation ids")
			if queue_ids != operation_ids:
				raise ModelRetry("Queue must preserve execution-plan operation order")
			if [item.position for item in output.queue] != list(range(1, len(operation_ids) + 1)):
				raise ModelRetry("Queue positions must start at 1 and increase in operation order")
			if any(operation_id not in operation_ids for operation_id in approval_operation_ids):
				raise ModelRetry("Approval prompts can only reference operations in the plan")
			if len(approval_operation_ids) != len(set(approval_operation_ids)):
				raise ModelRetry("An operation can only appear in one approval prompt")
			if any(item.security_group_id and item.security_group_id not in valid_group_ids for item in output.queue):
				raise ModelRetry("Queue security_group_id values must reference returned approval prompts")
			blocked_ids = {
				evaluation.operation_id
				for evaluation in output.operation_evaluations
				if evaluation.blocking_reasons
			}
			evaluation_by_id = {evaluation.operation_id: evaluation for evaluation in output.operation_evaluations}
			for operation_id, evaluation in evaluation_by_id.items():
				operation = operation_by_id[operation_id]
				deterministic = deterministic_evaluation_by_id[operation_id]
				if evaluation.operation_type != operation.operation_type:
					raise ModelRetry("Security evaluations must preserve each operation_type exactly")
				if evaluation.operation_family != operation.operation_family:
					raise ModelRetry("Security evaluations must preserve each operation_family exactly")
				if isinstance(operation, (CreateRecord, UpdateRecord, DeleteRecord)) and evaluation.permission_type != doctype_permission_type(operation):
					raise ModelRetry("DocType security evaluations must preserve the deterministic permission_type")
				if evaluation.security_group_key != deterministic.security_group_key:
					raise ModelRetry("Security evaluations must preserve deterministic security_group_key values")
				if evaluation.permission_allowed != deterministic.permission_allowed:
					raise ModelRetry("Security evaluations must preserve deterministic permission_allowed values")
				if evaluation.approval_required != deterministic.approval_required:
					raise ModelRetry("Security evaluations must preserve deterministic approval_required values")
				if evaluation.explicit_confirmation_required != deterministic.explicit_confirmation_required:
					raise ModelRetry("Security evaluations must preserve deterministic explicit confirmation requirements")
				if evaluation.risk_level != deterministic.risk_level or evaluation.risk_score != deterministic.risk_score:
					raise ModelRetry("Security evaluations must preserve deterministic risk levels and scores")
			if any(operation_id in blocked_ids for operation_id in approval_operation_ids):
				raise ModelRetry("Blocked operations cannot be included in approval prompts")
			for prompt in output.approval_prompts:
				prompt_evaluations = [evaluation_by_id[operation_id] for operation_id in prompt.operation_ids]
				if any(evaluation.explicit_confirmation_required for evaluation in prompt_evaluations):
					if not prompt.explicit_confirmation_required or not prompt.confirmation_phrase:
						raise ModelRetry("Approval prompts must preserve explicit confirmation requirements from operation evaluations")
				if prompt.risk_level in {"high", "critical"} and (not prompt.explicit_confirmation_required or not prompt.confirmation_phrase):
					raise ModelRetry("High and critical approval prompts require an explicit confirmation phrase")
			for item in output.queue:
				expected_group = approval_group_by_operation.get(item.operation_id)
				if expected_group and item.security_group_id != expected_group:
					raise ModelRetry("Queued operations in approval prompts must reference their approval group_id")
				if evaluation_by_id[item.operation_id].approval_required and item.operation_id not in blocked_ids and item.operation_id not in approval_group_by_operation:
					raise ModelRetry("Non-blocked operations that require approval must appear in an approval prompt")
			if blocked_ids and output.status != "blocked":
				raise ModelRetry("Security review status must be blocked when operations have blocking reasons")
			if output.approval_prompts and output.status != "waiting_for_approval" and not blocked_ids:
				raise ModelRetry("Security review with approvals should wait for approval")
			return output

	return _execution_security_agent


def get_orchestrator_agent(information_only=False):
	if information_only not in _orchestrator_agents:
		tools = [Tool(collect_information, sequential=True)]
		if not information_only:
			tools = [clarify_request, select_route, design_implementation, *tools]

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
				if state.stage != "waiting_for_user" or not state.user_clarification:
					raise ModelRetry("Call the current specialist stage before returning UserClarification")
				return state.user_clarification

			if isinstance(output, InformationAnswer):
				if state.stage not in {"clarification", "waiting_for_user"} and not information_only:
					raise ModelRetry("Do not return InformationAnswer during action routing; continue the current stage")
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

			if isinstance(output, RouteSelection):
				if state.stage != "implementation" or output != state.route_selection:
					raise ModelRetry("Return the exact RouteSelection produced by select_route")

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


def _required_tool_for_stage(stage):
	return {
		"clarification": "clarify_request",
		"waiting_for_user": "clarify_request",
		"route_selection": "select_route",
		"implementation": "design_implementation",
		"review": "review_outcome",
		"monitoring": "review_outcome",
	}.get(stage, "clarify_request")


def _is_temporary_dns_error(error):
	if isinstance(error, httpx.ConnectError):
		return "Temporary failure in name resolution" in str(error)
	return any(_is_temporary_dns_error(arg) for arg in getattr(error, "args", []) if isinstance(arg, BaseException))


def _is_temporary_transport_error(error):
	if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout, httpx.NetworkError)):
		return True
	return any(_is_temporary_transport_error(arg) for arg in getattr(error, "args", []) if isinstance(arg, BaseException))


def _is_temporary_ai_provider_error(error):
	if _is_temporary_dns_error(error) or _is_temporary_transport_error(error):
		return True
	if isinstance(error, ModelHTTPError):
		return error.status_code in {429, 500, 502, 503, 504}
	return any(_is_temporary_ai_provider_error(arg) for arg in getattr(error, "args", []) if isinstance(arg, BaseException))


def _network_pause_result(state, error):
	return OrchestrationRunResult(
		output=OrchestrationPaused(
			stage="clarification" if state.stage == "waiting_for_user" else state.stage,
			required_tool=_required_tool_for_stage(state.stage),
			reason=(
				"Temporary AI provider/network failure while contacting the model. "
				"No system records were changed. Retry the same command when DNS/network is available. "
				f"Error: {error}"
			),
		),
		state=state,
	)


def _usage_limit_pause_result(state, error):
	return OrchestrationRunResult(
		output=OrchestrationPaused(
			stage="clarification" if state.stage == "waiting_for_user" else state.stage,
			required_tool=_required_tool_for_stage(state.stage),
			reason=(
				"The AI run exceeded its token budget before completing this broad request. "
				"No system records were changed. Use a narrower request, or use a deterministic execution-security preview for approval grouping. "
				f"Error: {error}"
			),
		),
		state=state,
	)


def _run_agent_with_network_retry(agent, *, prompt, state, message_history):
	return _run_agent_sync_with_retry(
		agent,
		prompt=prompt,
		deps=state,
		conversation_id=state.conversation_id or state.orchestration_id,
		message_history=message_history,
	)


def _run_agent_sync_with_retry(agent, *, prompt, deps, conversation_id, message_history=None):
	last_error = None
	for attempt in range(3):
		try:
			return agent.run_sync(
				prompt,
				deps=deps,
				message_history=message_history,
				conversation_id=conversation_id,
				usage_limits=USAGE_LIMITS,
			)
		except Exception as error:
			if not _is_temporary_ai_provider_error(error):
				raise
			last_error = error
			logfire.warning(
				"temporary AI provider failure",
				conversation_id=conversation_id,
				attempt=attempt + 1,
				error=str(error),
			)
			if attempt < 2:
				time_module.sleep(2 ** attempt)
	raise last_error


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
		with logfire.span(
			"kratium orchestration run",
			**_safe_logfire_attributes(
				orchestration_id=state.orchestration_id,
				conversation_id=state.conversation_id or state.orchestration_id,
				stage=state.stage,
				information_only=is_information_only(state.input.input),
			),
		):
			logfire.info(
				"orchestration started",
				orchestration_id=state.orchestration_id,
				stage=state.stage,
				input=state.input.input,
			)
			result = _run_agent_with_network_retry(
				get_orchestrator_agent(information_only=is_information_only(state.input.input)),
				prompt=prompt,
				state=state,
				message_history=message_history,
			)
			logfire.info(
				"orchestration completed",
				orchestration_id=state.orchestration_id,
				output_type=type(result.output).__name__,
			)
	except Exception as error:
		if _is_temporary_ai_provider_error(error):
			result = None
			return _network_pause_result(state, error)
		if isinstance(error, UsageLimitExceeded):
			result = None
			return _usage_limit_pause_result(state, error)
		raise
	finally:
		logfire.force_flush(timeout_millis=5000)

	state.message_history = to_jsonable_python(result.all_messages())
	state.conversation_id = result.conversation_id

	return OrchestrationRunResult(output=result.output, state=state)


def preview_orchestration(final_input):
	result = start_orchestration(final_input)
	remember_orchestration_result(result)
	return summarize_orchestration_result(result)


def preview_route_selection(final_input, goal=None):
	state = OrchestrationState(
		orchestration_id=str(uuid4()),
		stage="route_selection",
		input=OrchestrationInput(input=final_input, source="direct"),
		clarification=ClarificationResult(
			problem=ProblemBreakdown(goal=goal or final_input),
			evidence=[Evidence(source="input", reference="direct input", fact=final_input)],
			confidence=0.9,
		),
	)
	result = run_orchestrator(state)
	remember_orchestration_result(result)
	return summarize_orchestration_result(result)


def preview_doctype_field_plan(doctype, operation_type, goal, known_values=None):
	state = OrchestrationState(
		orchestration_id=str(uuid4()),
		stage="implementation",
		input=OrchestrationInput(input=goal, source="direct"),
	)
	plan = plan_doctype_fields_for_operation(
		{"deps": state},
		doctype=doctype,
		operation_type=operation_type,
		goal=goal,
		known_values=known_values or {},
	)
	return {
		"doctype": plan.doctype,
		"operation_type": plan.operation_type,
		"required_fields": plan.required_fields,
		"relevant_fields": plan.relevant_fields,
		"avoid_fields": plan.avoid_fields,
		"field_types": plan.field_types,
		"select_options": plan.select_options,
		"field_guidance": plan.field_guidance,
		"system_notes": plan.system_notes,
	}


def _orchestration_cache_key(orchestration_id):
	return f"kratium_orchestration_state:{orchestration_id}"


def _execution_preparation_cache_key(plan_id):
	return f"kratium_execution_preparation:{plan_id}"


def _execution_plan_cache_key(plan_id):
	return f"kratium_execution_plan:{plan_id}"


def _execution_sync_report_cache_key(plan_id):
	return f"kratium_execution_sync_report:{plan_id}"


def remember_orchestration_result(result):
	try:
		import frappe

		frappe.cache().set_value(
			_orchestration_cache_key(result.state.orchestration_id),
			result.state.model_dump_json(),
			expires_in_sec=3600,
		)
	except Exception as error:
		logfire.warning(
			"failed to cache orchestration state",
			orchestration_id=result.state.orchestration_id,
			error=str(error),
		)
	return result


def remember_execution_preparation(preparation):
	try:
		import frappe

		preparation = ExecutionPreparation.model_validate(preparation)
		frappe.cache().set_value(
			_execution_preparation_cache_key(preparation.plan_id),
			preparation.model_dump_json(),
			expires_in_sec=3600,
		)
	except Exception as error:
		logfire.warning(
			"failed to cache execution preparation",
			plan_id=getattr(preparation, "plan_id", None),
			error=str(error),
		)
	return preparation


def remember_execution_plan(plan):
	try:
		import frappe

		plan = ExecutionPlan.model_validate(plan)
		frappe.cache().set_value(
			_execution_plan_cache_key(plan.plan_id),
			plan.model_dump_json(),
			expires_in_sec=3600,
		)
	except Exception as error:
		logfire.warning(
			"failed to cache execution plan",
			plan_id=getattr(plan, "plan_id", None),
			error=str(error),
		)
	return plan


def get_cached_execution_preparation(plan_id):
	import frappe

	preparation_json = frappe.cache().get_value(_execution_preparation_cache_key(plan_id))
	if not preparation_json:
		raise ValueError(f"No cached execution preparation found for {plan_id}")
	return ExecutionPreparation.model_validate_json(preparation_json)


def get_cached_execution_plan(plan_id):
	import frappe

	plan_json = frappe.cache().get_value(_execution_plan_cache_key(plan_id))
	if not plan_json:
		raise ValueError(f"No cached execution plan found for {plan_id}")
	return ExecutionPlan.model_validate_json(plan_json)


def remember_execution_sync_report(report):
	try:
		import frappe

		report = ExecutionSyncReport.model_validate(report)
		frappe.cache().set_value(
			_execution_sync_report_cache_key(report.plan_id),
			report.model_dump_json(),
			expires_in_sec=3600,
		)
	except Exception as error:
		logfire.warning(
			"failed to cache execution sync report",
			plan_id=getattr(report, "plan_id", None),
			error=str(error),
		)
	return report


def get_cached_execution_sync_report(plan_id):
	import frappe

	report_json = frappe.cache().get_value(_execution_sync_report_cache_key(plan_id))
	if not report_json:
		return None
	return ExecutionSyncReport.model_validate_json(report_json)


def get_cached_orchestration_state(orchestration_id):
	import frappe

	state_json = frappe.cache().get_value(_orchestration_cache_key(orchestration_id))
	if not state_json:
		raise ValueError(f"No cached orchestration state found for {orchestration_id}")
	return OrchestrationState.model_validate_json(state_json)


def continue_cached_orchestration(orchestration_id, answer):
	state = get_cached_orchestration_state(orchestration_id)
	result = continue_orchestration_with_answer(state, answer)
	remember_orchestration_result(result)
	return result


def preview_continue_cached_orchestration(orchestration_id, answer):
	return summarize_orchestration_result(continue_cached_orchestration(orchestration_id, answer))


def route_selection_to_user_clarification(route_selection):
	chosen_route = next(
		route for route in route_selection.routes if route.route_id == route_selection.chosen_route_id
	)
	missing_information = chosen_route.missing_information or chosen_route.risks
	question = "What should I know before choosing the implementation route?"
	if missing_information:
		question = "Please clarify: " + "; ".join(missing_information)

	return UserClarification(
		questions=[
			UserQuestion(
				question=question,
				reason="Route selection found missing information that changes the safest implementation path.",
			)
		],
		blocked_decisions=[decision.conclusion for decision in route_selection.decisions],
	)


def detect_requested_intents(text):
	text = (text or "").lower()
	create_terms = {"add", "create", "schedule", "make", "insert", "record", "plan"}
	update_terms = {"update", "change", "move", "reschedule", "rename", "mark", "complete"}
	delete_terms = {"delete", "remove", "clear", "cancel"}
	read_terms = {"check", "show", "what", "list", "find", "look", "planned"}
	intents = {
		"create": any(term in text for term in create_terms),
		"update": any(term in text for term in update_terms),
		"delete": any(term in text for term in delete_terms),
		"read": any(term in text for term in read_terms),
	}
	mutation_intents = [name for name in ("create", "update", "delete") if intents[name]]
	return {
		"create": intents["create"],
		"update": intents["update"],
		"delete": intents["delete"],
		"read": intents["read"],
		"mutation_intents": mutation_intents,
	}


def missing_route_intents_for_choice(intent, chosen_route):
	if chosen_route.outcome_type == "plan":
		return []
	missing = []
	if intent["create"] and chosen_route.outcome_type != "create":
		missing.append("create")
	if intent["update"] and chosen_route.outcome_type not in {"update", "reschedule", "classify"}:
		missing.append("update")
	if intent["delete"] and chosen_route.outcome_type != "delete":
		missing.append("delete")
	if intent["read"] and chosen_route.outcome_type not in {"read", "delete", "update", "plan"}:
		missing.append("read/check")
	return missing


def missing_operation_intents_for_design(intent, design):
	operation_types = {operation.operation_type for operation in design.operations}
	decision_text = "\n".join(
		f"{decision.question} {decision.conclusion} {' '.join(decision.alternatives)}"
		for decision in design.decisions
	).lower()
	missing = []
	if intent["create"] and "doctype.create" not in operation_types:
		missing.append("create")
	if intent["update"] and "doctype.update" not in operation_types and "scheduler.run" not in operation_types:
		missing.append("update")
	if intent["delete"] and "doctype.delete" not in operation_types:
		no_records_found = any(
			phrase in decision_text
			for phrase in ("no matching", "none found", "no records", "nothing to delete", "no actions found")
		)
		if not no_records_found:
			missing.append("delete")
	return missing


def is_placeholder_record_id(record_id):
	if not record_id:
		return True
	text = str(record_id).lower().strip()
	placeholder_terms = {
		"non_existent",
		"nonexistent",
		"placeholder",
		"dummy",
		"fake",
		"sample",
		"unknown",
		"todo",
		"n/a",
		"none",
	}
	return any(term in text for term in placeholder_terms)


def is_malformed_record_id(record_id):
	if not record_id:
		return False
	text = str(record_id).strip()
	return any(token in text for token in ['"', "'", "{", "}", "[", "]", "\n", "\r"])


def is_broad_destructive_request(text):
	lower = (text or "").lower()
	if not any(word in lower for word in ("delete", "remove", "clear")):
		return False
	return bool(re.search(r"\b(all|every|everything)\b", lower) or "other than" in lower or re.search(r"\bexcept\b", lower))


def assumption_review_to_clarification(review):
	return ClarificationResult(
		problem=ProblemBreakdown(
			goal=review.clarified_goal,
			assumptions=[
				decision.assumption
				for decision in review.decisions
				if decision.action in {"use_assumption", "notify_user"}
			],
			information_needed=[question.question for question in review.remaining_questions],
		),
		evidence=[evidence for decision in review.decisions for evidence in decision.evidence],
		confidence=review.confidence,
	)


def assumption_review_to_user_clarification(review):
	return UserClarification(
		questions=review.remaining_questions,
		blocked_decisions=review.blocked_decisions or [
			decision.reason for decision in review.decisions if decision.action == "ask_user"
		] or ["Assumption review still needs user input before the workflow can continue."],
	)


def build_assumption_notifications(review):
	notifications = []
	for decision in review.decisions:
		if decision.action != "notify_user":
			continue
		notifications.append(AssumptionNotification(
			message=f"I assumed: {decision.assumption}",
			assumption=decision.assumption,
			question=decision.question,
			confidence=decision.confidence,
		))
	return notifications


def apply_user_clarification_answer(state, answer):
	state = OrchestrationState.model_validate(state)
	answer_text = answer if isinstance(answer, str) else json.dumps(to_jsonable_python(answer))
	state.input.context = {
		**state.input.context,
		"user_clarification_answer": answer_text,
		"previous_user_clarification": (
			state.user_clarification.model_dump() if state.user_clarification else None
		),
	}
	state.stage = "clarification"
	return state


def continue_orchestration_with_answer(state, answer):
	state = apply_user_clarification_answer(state, answer)
	if state.stage == "waiting_for_user" and state.user_clarification:
		return OrchestrationRunResult(output=state.user_clarification, state=state)
	return run_orchestrator(state, new_information=answer)


def preview_continue_orchestration_with_answer(state, answer):
	return summarize_orchestration_result(continue_orchestration_with_answer(state, answer))


def summarize_orchestration_result(result):
	result = OrchestrationRunResult.model_validate(result)
	output = result.output
	summary = {
		"stage": result.state.stage,
		"status": output.status,
		"orchestration_id": result.state.orchestration_id,
		"conversation_id": result.state.conversation_id,
	}

	if isinstance(output, InformationAnswer):
		summary["results"] = [
			{
				"status": item.status,
				"answer": item.answer,
				"confidence": item.confidence,
				"strategy": item.strategy,
				"facts": [fact.model_dump() for fact in item.facts],
				"missing_information": item.missing_information,
			}
			for item in output.results
		]
	elif isinstance(output, UserClarification):
		summary["questions"] = [question.model_dump() for question in output.questions]
		summary["blocked_decisions"] = output.blocked_decisions
	elif isinstance(output, RouteSelection):
		summary["chosen_route_id"] = output.chosen_route_id
		summary["routes"] = [route.model_dump() for route in output.routes]
		summary["decisions"] = [decision.model_dump() for decision in output.decisions]
	elif isinstance(output, OrchestrationPaused):
		summary["required_tool"] = output.required_tool
		summary["reason"] = output.reason
	elif isinstance(output, ExecutionPlan):
		summary["plan_id"] = output.plan_id
		summary["operation_count"] = len(output.operations)
		summary["chosen_route_id"] = output.chosen_route_id
		summary["execution_plan"] = output.model_dump()
		summary["operations"] = [summarize_execution_operation(operation) for operation in output.operations]
		summary["success_criteria"] = [criterion.model_dump() for criterion in output.success_criteria]

	if result.state.route_selection:
		chosen_route = next(
			(
				route
				for route in result.state.route_selection.routes
				if route.route_id == result.state.route_selection.chosen_route_id
			),
			None,
		)
		summary["route_selection"] = {
			"chosen_route_id": result.state.route_selection.chosen_route_id,
			"routes_considered": len(result.state.route_selection.routes),
			"decisions": len(result.state.route_selection.decisions),
		}
		if chosen_route:
			summary["route_selection"].update({
				"outcome_type": chosen_route.outcome_type,
				"score": chosen_route.score,
				"confidence": chosen_route.confidence,
				"system_objects": chosen_route.system_objects,
				"risks": chosen_route.risks,
			})
	if result.state.information:
		summary["information_requests"] = len(result.state.information)
	if result.state.assumption_review:
		summary["assumptions"] = [
			decision.model_dump() for decision in result.state.assumption_review.decisions
		]
	if result.state.assumption_notifications:
		summary["assumption_notifications"] = [
			notification.model_dump() for notification in result.state.assumption_notifications
		]

	return summary


def summarize_execution_operation(operation):
	base = {
		"operation_type": operation.operation_type,
		"operation_family": operation.operation_family,
		"operation_id": operation.operation_id,
		"decision_id": operation.decision_id,
		"description": operation.description,
		"dependencies": [dependency.model_dump() for dependency in operation.dependencies],
	}
	if isinstance(operation, CreateRecord):
		return {
			**base,
			"doctype": operation.doctype,
			"fields": _json_safe(operation.fields),
		}
	if isinstance(operation, UpdateRecord):
		return {
			**base,
			"doctype": operation.doctype,
			"record_id": operation.record_id,
			"expected_modified": operation.expected_modified.isoformat(),
			"fields": _json_safe(operation.fields),
		}
	if isinstance(operation, DeleteRecord):
		return {
			**base,
			"doctype": operation.doctype,
			"record_id": operation.record_id,
			"expected_modified": operation.expected_modified.isoformat() if operation.expected_modified else None,
		}
	return _json_safe(operation.model_dump())


def resume_orchestration(state, new_information):
	state = OrchestrationState.model_validate(state)

	if isinstance(new_information, dict) and "answered_questions" in new_information:
		new_information = UserClarificationAnswer.model_validate(new_information)
	elif isinstance(new_information, dict) and {"plan_id", "results"} <= set(new_information):
		new_information = ExecutionReport.model_validate(new_information)

	if isinstance(new_information, str):
		new_information = build_user_clarification_answer(state, new_information)

	if isinstance(new_information, UserClarificationAnswer):
		if state.stage != "waiting_for_user" or not state.user_clarification:
			raise ValueError("User clarification answers can only resume a waiting orchestration")
		state.stage = "clarification"
		state.user_clarification = None

	if isinstance(new_information, ExecutionReport):
		state.execution_report = new_information
		state.stage = "review"

	return run_orchestrator(state, new_information)


def build_user_clarification_answer(state, answer):
	state = OrchestrationState.model_validate(state)
	if state.stage != "waiting_for_user" or not state.user_clarification:
		raise ValueError("There is no active user clarification to answer")

	return UserClarificationAnswer(
		answered_questions=[
			{
				"question": question.question,
				"reason": question.reason,
				"answer": answer,
			}
			for question in state.user_clarification.questions
		],
		freeform_answer=answer,
	)


def answer_user_clarification(result, answer):
	result = OrchestrationRunResult.model_validate(result)
	return resume_orchestration(result.state, build_user_clarification_answer(result.state, answer))

# endregion 2. ORCHESTRATOR


# region 2. HANDOFFS
def request_user_clarification(state, clarification):
	# Pauses the stream and resumes it when the user's answer is available.
	pass


def compile_execution_plan(state):
	state = OrchestrationState.model_validate(state)
	if not state.clarification or not state.route_selection or not state.action_design:
		raise ValueError("Clarification, route selection, and action design are required")
	decisions = merge_plan_decisions(state.route_selection.decisions, state.action_design.decisions, state.action_design.operations)
	operations = normalize_plan_operation_dependencies(state.action_design.operations)

	return ExecutionPlan(
		plan_id=str(uuid4()),
		problem=state.clarification.problem,
		routes_considered=state.route_selection.routes,
		chosen_route_id=state.route_selection.chosen_route_id,
		decisions=decisions,
		operations=operations,
		success_criteria=state.action_design.success_criteria,
	)


def normalize_plan_operation_dependencies(operations):
	operation_ids = set()
	normalized = []
	for operation in operations:
		if isinstance(operation, (CreateRecord, UpdateRecord)):
			operation = add_dependencies_for_operation_id_fields(operation, operation_ids)
		elif isinstance(operation, DeleteRecord):
			operation = normalize_delete_operation_dependency(operation, operation_ids)
		normalized.append(operation)
		operation_ids.add(operation.operation_id)
	return normalized


def add_dependencies_for_operation_id_fields(operation, prior_operation_ids):
	dependencies = list(operation.dependencies)
	dependency_ids = {dependency.operation_id for dependency in dependencies if dependency.operation_id}
	for operation_id in sorted(find_same_plan_operation_references(operation.fields, prior_operation_ids)):
		if operation_id not in dependency_ids:
			dependencies.append(OperationDependency(target="operation", operation_id=operation_id))
			dependency_ids.add(operation_id)
	if dependencies == operation.dependencies:
		return operation
	return operation.model_copy(update={"dependencies": dependencies})


def normalize_delete_operation_dependency(operation, prior_operation_ids):
	if not is_same_plan_operation_reference(operation.record_id, prior_operation_ids):
		return operation
	dependencies = list(operation.dependencies)
	if not any(dependency.operation_id == operation.record_id for dependency in dependencies):
		dependencies.append(OperationDependency(target="operation", operation_id=operation.record_id))
	return operation.model_copy(update={"record_id": None, "dependencies": dependencies})


def is_same_plan_operation_reference(value, prior_operation_ids):
	return isinstance(value, str) and value in prior_operation_ids


def find_same_plan_operation_references(value, prior_operation_ids):
	if is_same_plan_operation_reference(value, prior_operation_ids):
		return {value}
	if isinstance(value, dict):
		operation_ids = set()
		for child_value in value.values():
			operation_ids.update(find_same_plan_operation_references(child_value, prior_operation_ids))
		return operation_ids
	if isinstance(value, list):
		operation_ids = set()
		for child_value in value:
			operation_ids.update(find_same_plan_operation_references(child_value, prior_operation_ids))
		return operation_ids
	return set()


def merge_plan_decisions(route_decisions, implementation_decisions, operations):
	merged_decisions = list(route_decisions)
	used_ids = {decision.decision_id for decision in merged_decisions}
	id_map = {}

	for decision in implementation_decisions:
		original_id = decision.decision_id
		if original_id in used_ids:
			new_id = f"implementation_{original_id}"
			counter = 2
			while new_id in used_ids:
				new_id = f"implementation_{original_id}_{counter}"
				counter += 1
			decision = decision.model_copy(update={"decision_id": new_id})
			id_map[original_id] = new_id
		used_ids.add(decision.decision_id)
		merged_decisions.append(decision)

	for operation in operations:
		if operation.decision_id in id_map:
			operation.decision_id = id_map[operation.decision_id]

	return merged_decisions


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


# region 1. SCHEMAS
SecurityRiskLevel = Literal["low", "medium", "high", "critical"]


class OperationSecurityEvaluation(Schema):
	operation_id: str
	operation_type: str
	operation_family: str
	security_group_key: str
	permission_type: str | None = None
	permission_allowed: bool = True
	risk_level: SecurityRiskLevel
	risk_score: float = Field(ge=0, le=1)
	approval_required: bool = True
	explicit_confirmation_required: bool = False
	reasons: list[str] = Field(default_factory=list)
	blocking_reasons: list[str] = Field(default_factory=list)
	record_snapshot: dict[str, Any] | None = None


class ExecutionApprovalPrompt(Schema):
	group_id: str
	group_key: str
	title: str
	operation_ids: list[str] = Field(min_length=1)
	risk_level: SecurityRiskLevel
	risk_score: float = Field(ge=0, le=1)
	permission_types: list[str] = Field(default_factory=list)
	prompt: str
	reasons: list[str] = Field(default_factory=list)
	explicit_confirmation_required: bool = False
	confirmation_phrase: str | None = None


class ExecutionQueueItem(Schema):
	position: int
	operation_id: str
	security_group_id: str | None = None
	blocked: bool = False
	blocking_reasons: list[str] = Field(default_factory=list)


class ExecutionSecurityReview(Schema):
	plan_id: str
	status: Literal["ready_to_execute", "waiting_for_approval", "blocked"]
	overall_risk_level: SecurityRiskLevel
	overall_risk_score: float = Field(ge=0, le=1)
	operation_evaluations: list[OperationSecurityEvaluation]
	approval_prompts: list[ExecutionApprovalPrompt]
	queue: list[ExecutionQueueItem]
	blocked_reasons: list[str] = Field(default_factory=list)


class ExecutionPreparation(Schema):
	plan_id: str
	status: Literal["ready_to_execute", "waiting_for_approval", "blocked"]
	security_review: ExecutionSecurityReview


class ExecutionApprovalDecision(Schema):
	group_id: str
	approved: bool
	confirmation_phrase: str | None = None
	note: str | None = None


class ExecutionApprovalResult(Schema):
	plan_id: str
	status: Literal["ready_to_execute", "waiting_for_approval", "blocked", "rejected"]
	approved_group_ids: list[str] = Field(default_factory=list)
	rejected_group_ids: list[str] = Field(default_factory=list)
	missing_group_ids: list[str] = Field(default_factory=list)
	invalid_approval_reasons: list[str] = Field(default_factory=list)
	queue: list[ExecutionQueueItem]
	ready_operation_ids: list[str] = Field(default_factory=list)
	waiting_operation_ids: list[str] = Field(default_factory=list)
	blocked_operation_ids: list[str] = Field(default_factory=list)


class AtomicSyncResult(Schema):
	operation_id: str
	operation_type: str
	operation_family: str
	status: Literal["success", "skipped", "failed", "rolled_back"]
	message: str
	record: dict[str, Any] | None = None
	before: dict[str, Any] | None = None
	after: dict[str, Any] | None = None
	output: dict[str, Any] = Field(default_factory=dict)
	error: str | None = None


class ExecutionSyncReport(Schema):
	plan_id: str
	status: Literal["complete", "partial", "failed", "blocked"]
	executed_operation_ids: list[str] = Field(default_factory=list)
	skipped_operation_ids: list[str] = Field(default_factory=list)
	failed_operation_ids: list[str] = Field(default_factory=list)
	results: list[AtomicSyncResult]
	message: str


# endregion 1. SCHEMAS


# region 1. PROCESS
def execute_plan(plan):
	# Execution always starts with security preparation. Sync requires explicit approval intake.
	return prepare_execution(plan)


def prepare_execution(plan):
	plan = ExecutionPlan.model_validate(plan)
	plan = normalize_execution_plan_for_security(plan)
	remember_execution_plan(plan)
	review = run_execution_security_agent(plan)
	return ExecutionPreparation(
		plan_id=plan.plan_id,
		status=review.status,
		security_review=review,
	)


def normalize_execution_plan_for_security(plan):
	plan = plan.model_copy(update={"operations": normalize_plan_operation_dependencies(plan.operations)})
	updates = []
	changed = False
	for operation in plan.operations:
		if isinstance(operation, DeleteRecord) and operation.record_id and is_malformed_record_id(operation.record_id):
			clean_record_id = extract_existing_record_id_from_malformed(operation.doctype, operation.record_id)
			if clean_record_id and clean_record_id != operation.record_id:
				operation = operation.model_copy(update={"record_id": clean_record_id})
				changed = True
		if isinstance(operation, (UpdateRecord, DeleteRecord)) and operation.record_id and not is_malformed_record_id(operation.record_id):
			current_modified = get_current_record_modified(operation.doctype, operation.record_id)
			if current_modified and not expected_modified_matches(current_modified, operation.expected_modified):
				operation = operation.model_copy(update={"expected_modified": current_modified})
				changed = True
		updates.append(operation)
	if not changed:
		return plan
	return plan.model_copy(update={"operations": updates})


def get_current_record_modified(doctype, record_id):
	try:
		import frappe

		modified = frappe.db.get_value(doctype, record_id, "modified")
		return _coerce_datetime(modified) if modified else None
	except Exception:
		return None


def extract_existing_record_id_from_malformed(doctype, record_id):
	text = str(record_id or "")
	try:
		import frappe

		for name in frappe.get_all(doctype, pluck="name", limit_page_length=500):
			if name and name in text:
				return name
	except Exception:
		return None
	return None


def explain_malformed_record_id(operation):
	recovered = extract_existing_record_id_from_malformed(operation.doctype, operation.record_id)
	if recovered:
		return None
	return (
		f"Malformed delete/update target for {operation.operation_id}. "
		"The AI produced text that is not an exact record id, so execution was blocked before mutation. "
		"Retry with a specific record/action name or a deterministic filter."
	)


def request_execution_approval(preparation):
	preparation = ExecutionPreparation.model_validate(preparation)
	return preparation.security_review.approval_prompts


def apply_execution_approvals(preparation, decisions):
	preparation = ExecutionPreparation.model_validate(preparation)
	decisions = [ExecutionApprovalDecision.model_validate(decision) for decision in decisions]
	review = preparation.security_review
	prompt_by_id = {prompt.group_id: prompt for prompt in review.approval_prompts}
	decision_by_id = {decision.group_id: decision for decision in decisions}
	invalid_reasons = []
	approved_group_ids = []
	rejected_group_ids = []

	if review.status == "blocked":
		return build_execution_approval_result(
			preparation,
			approved_group_ids=[],
			rejected_group_ids=[],
			invalid_reasons=review.blocked_reasons or ["Execution preparation is blocked."],
		)

	for decision in decisions:
		prompt = prompt_by_id.get(decision.group_id)
		if not prompt:
			invalid_reasons.append(f"Unknown approval group: {decision.group_id}")
			continue
		if not decision.approved:
			rejected_group_ids.append(decision.group_id)
			continue
		if prompt.explicit_confirmation_required and decision.confirmation_phrase != prompt.confirmation_phrase:
			invalid_reasons.append(
				f"Approval group {decision.group_id} requires confirmation phrase: {prompt.confirmation_phrase}"
			)
			continue
		approved_group_ids.append(decision.group_id)

	return build_execution_approval_result(
		preparation,
		approved_group_ids=approved_group_ids,
		rejected_group_ids=rejected_group_ids,
		invalid_reasons=invalid_reasons,
	)


def build_execution_approval_result(preparation, approved_group_ids, rejected_group_ids, invalid_reasons):
	review = preparation.security_review
	approved_groups = set(approved_group_ids)
	rejected_groups = set(rejected_group_ids)
	required_groups = {prompt.group_id for prompt in review.approval_prompts}
	missing_groups = sorted(required_groups - approved_groups - rejected_groups)
	operation_evaluations = {evaluation.operation_id: evaluation for evaluation in review.operation_evaluations}
	ready_operation_ids = []
	waiting_operation_ids = []
	blocked_operation_ids = []

	for item in review.queue:
		evaluation = operation_evaluations[item.operation_id]
		if item.blocked or evaluation.blocking_reasons:
			blocked_operation_ids.append(item.operation_id)
		elif item.security_group_id in rejected_groups:
			blocked_operation_ids.append(item.operation_id)
		elif item.security_group_id in approved_groups or not evaluation.approval_required:
			ready_operation_ids.append(item.operation_id)
		else:
			waiting_operation_ids.append(item.operation_id)

	if invalid_reasons or review.status == "blocked":
		status = "blocked"
	elif waiting_operation_ids or missing_groups:
		status = "waiting_for_approval"
	elif rejected_groups and not ready_operation_ids:
		status = "rejected"
	else:
		status = "ready_to_execute"

	return ExecutionApprovalResult(
		plan_id=preparation.plan_id,
		status=status,
		approved_group_ids=sorted(approved_groups),
		rejected_group_ids=sorted(rejected_groups),
		missing_group_ids=missing_groups,
		invalid_approval_reasons=invalid_reasons,
		queue=review.queue,
		ready_operation_ids=ready_operation_ids,
		waiting_operation_ids=waiting_operation_ids,
		blocked_operation_ids=blocked_operation_ids,
	)


def sync_approved_execution(plan, approval_result):
	plan = ExecutionPlan.model_validate(plan)
	approval_result = ExecutionApprovalResult.model_validate(approval_result)
	cached_report = get_cached_execution_sync_report(plan.plan_id)
	if cached_report and cached_report.status == "complete":
		return cached_report
	if approval_result.plan_id != plan.plan_id:
		raise ValueError("Approval result plan_id must match execution plan")
	if approval_result.status != "ready_to_execute":
		return build_execution_report(
			plan,
			[],
			summary_status="blocked",
			message=f"Execution is not approved: {approval_result.status}",
			skipped_operation_ids=approval_result.waiting_operation_ids + approval_result.blocked_operation_ids,
		)

	operation_by_id = {operation.operation_id: operation for operation in plan.operations}
	results = []
	for operation_id in approval_result.ready_operation_ids:
		operation = operation_by_id.get(operation_id)
		if not operation:
			results.append(AtomicSyncResult(
				operation_id=operation_id,
				operation_type="unknown",
				operation_family="unknown",
				status="failed",
				message="Approved operation was not found in the execution plan.",
				error="Missing operation in plan.",
			))
			break
		try:
			operation = resolve_operation_dependencies(operation, results)
			result = execute_atomic_action(operation)
		except Exception as error:
			result = failed_sync_result(operation, error)
		results.append(result)
		if result.status == "failed":
			break

	return remember_execution_sync_report(build_execution_report(
		plan,
		results,
		skipped_operation_ids=[
			operation.operation_id
			for operation in plan.operations
			if operation.operation_id not in {result.operation_id for result in results}
		],
	))


def execute_atomic_action(operation):
	if isinstance(operation, CreateRecord):
		return sync_create_record(operation)
	if isinstance(operation, UpdateRecord):
		return sync_update_record(operation)
	if isinstance(operation, DeleteRecord):
		return sync_delete_record(operation)
	if isinstance(operation, RunReport):
		return sync_run_report(operation)
	if isinstance(operation, RefreshDashboard):
		return sync_refresh_dashboard(operation)
	if isinstance(operation, RunScheduler):
		return sync_run_scheduler(operation)
	if isinstance(operation, SendNotification):
		return sync_send_notification(operation)
	if isinstance(operation, ExternalCall):
		return sync_external_call(operation)
	raise ValueError(f"Unsupported operation type: {operation.operation_type}")


def resolve_operation_dependencies(operation, prior_results):
	result_by_operation = {result.operation_id: result for result in prior_results}
	if isinstance(operation, (CreateRecord, UpdateRecord)):
		return resolve_field_operation_references(operation, result_by_operation)
	if not isinstance(operation, DeleteRecord) or operation.record_id:
		return operation
	for dependency in operation.dependencies:
		if dependency.target != "operation":
			continue
		result = result_by_operation.get(dependency.operation_id)
		if not result or result.status != "success" or not result.record:
			raise ValueError(f"Dependency {dependency.operation_id} did not produce a record to delete")
		return operation.model_copy(update={
			"record_id": result.record.get("name"),
			"expected_modified": _coerce_datetime((result.after or {}).get("modified")),
		})
	raise ValueError(f"Delete operation {operation.operation_id} has no resolved record_id")


def resolve_field_operation_references(operation, result_by_operation):
	fields = dict(operation.fields)
	changed = False
	for dependency in operation.dependencies:
		if dependency.target != "operation" or not dependency.operation_id:
			continue
		result = require_successful_operation_result(result_by_operation, dependency.operation_id)
		for fieldname in operation_dependency_target_fields(operation.doctype, result.record.get("doctype")):
			if should_fill_dependency_target_field(operation.doctype, fieldname, fields, dependency.operation_id):
				fields[fieldname] = result.record.get("name")
				changed = True
				break
	fields, nested_changed = replace_operation_references_in_value(fields, result_by_operation)
	changed = changed or nested_changed
	if not changed:
		return operation
	return operation.model_copy(update={"fields": fields})


def replace_operation_references_in_value(value, result_by_operation):
	if isinstance(value, str) and value in result_by_operation:
		result = require_successful_operation_result(result_by_operation, value)
		return result.record.get("name"), True
	if isinstance(value, dict):
		changed = False
		updated = {}
		for key, child_value in value.items():
			updated_value, child_changed = replace_operation_references_in_value(child_value, result_by_operation)
			updated[key] = updated_value
			changed = changed or child_changed
		return updated, changed
	if isinstance(value, list):
		changed = False
		updated = []
		for child_value in value:
			updated_value, child_changed = replace_operation_references_in_value(child_value, result_by_operation)
			updated.append(updated_value)
			changed = changed or child_changed
		return updated, changed
	return value, False


def should_fill_dependency_target_field(doctype, fieldname, fields, dependency_operation_id):
	current_value = fields.get(fieldname)
	if current_value == dependency_operation_id:
		return True
	if fieldname in tree_parent_fieldnames(_get_sync_meta(doctype)):
		return current_value in {None, "", dependency_operation_id}
	return False


def operation_dependency_target_fields(doctype, dependency_doctype=None):
	meta = _get_sync_meta(doctype)
	fields = []
	for fieldname in tree_parent_fieldnames(meta):
		fields.append(fieldname)
	for field in meta.fields:
		if not _is_real_doctype_field(field) or not _is_writable_field(field):
			continue
		if field.fieldtype == "Link" and (not dependency_doctype or field.options == dependency_doctype):
			fields.append(field.fieldname)
		elif field.fieldtype == "Dynamic Link":
			fields.append(field.fieldname)
	return _dedupe_strings(fields)


def tree_parent_fieldnames(meta):
	fieldnames = []
	if getattr(meta, "is_tree", False):
		fieldnames.extend([getattr(meta, "nsm_parent_field", None), f"parent_{meta.name.lower().replace(' ', '_')}"])
	if meta.name == "Action":
		fieldnames.extend(["parent_action", "ancestor"])
	fieldnames.extend(["parent", "parent_record", "parent_doc"])
	return [fieldname for fieldname in fieldnames if fieldname]


def _dedupe_strings(values):
	seen = set()
	deduped = []
	for value in values:
		if value and value not in seen:
			deduped.append(value)
			seen.add(value)
	return deduped


def require_successful_operation_result(result_by_operation, operation_id):
	result = result_by_operation.get(operation_id)
	if not result or result.status != "success" or not result.record:
		raise ValueError(f"Dependency {operation_id} did not produce a record")
	return result


def build_execution_report(plan, results, summary_status=None, message=None, skipped_operation_ids=None):
	results = [AtomicSyncResult.model_validate(result) for result in results]
	executed_operation_ids = [result.operation_id for result in results if result.status == "success"]
	failed_operation_ids = [result.operation_id for result in results if result.status == "failed"]
	skipped_operation_ids = skipped_operation_ids or []
	if summary_status:
		status = summary_status
	elif failed_operation_ids and executed_operation_ids:
		status = "partial"
	elif failed_operation_ids:
		status = "failed"
	else:
		status = "complete"
	return ExecutionSyncReport(
		plan_id=plan.plan_id,
		status=status,
		executed_operation_ids=executed_operation_ids,
		skipped_operation_ids=skipped_operation_ids,
		failed_operation_ids=failed_operation_ids,
		results=results,
		message=message or build_execution_report_message(status, results, skipped_operation_ids),
	)


def build_execution_report_message(status, results, skipped_operation_ids):
	if status == "complete":
		return f"Execution complete: {len(results)} operation(s) synced."
	if status == "partial":
		return f"Execution partially completed: {len(results)} attempted, {len(skipped_operation_ids)} skipped."
	if status == "failed":
		return "Execution failed before completing approved operations."
	return "Execution did not run because approval or security requirements are not satisfied."


def rollback_execution(results):
	# Rollback is intentionally deferred. Frappe transaction rollback handles same-request failures.
	return [result.model_dump() if isinstance(result, AtomicSyncResult) else result for result in results]


def sync_create_record(operation):
	import frappe

	try:
		validate_doctype_operation_fields(operation)
		doc = frappe.new_doc(operation.doctype)
		doc.update(coerce_operation_fields_for_sync(operation.doctype, operation.fields))
		doc.insert()
		frappe.db.commit()
		after = _json_safe(doc.as_dict())
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Created {operation.doctype} {doc.name}.",
			record={"doctype": operation.doctype, "name": doc.name},
			after=after,
		)
	except Exception as error:
		frappe.db.rollback()
		return failed_sync_result(operation, error)


def sync_update_record(operation):
	import frappe

	try:
		validate_doctype_operation_fields(operation)
		doc = frappe.get_doc(operation.doctype, operation.record_id)
		before = _json_safe(doc.as_dict())
		validate_stale_record(operation, before.get("modified"))
		doc.update(coerce_operation_fields_for_sync(operation.doctype, operation.fields))
		doc.save()
		frappe.db.commit()
		after = _json_safe(doc.as_dict())
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Updated {operation.doctype} {operation.record_id}.",
			record={"doctype": operation.doctype, "name": operation.record_id},
			before=before,
			after=after,
		)
	except Exception as error:
		frappe.db.rollback()
		return failed_sync_result(operation, error)


def sync_delete_record(operation):
	import frappe

	try:
		doc = frappe.get_doc(operation.doctype, operation.record_id)
		before = _json_safe(doc.as_dict())
		validate_stale_record(operation, before.get("modified"))
		frappe.delete_doc(operation.doctype, operation.record_id)
		frappe.db.commit()
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Deleted {operation.doctype} {operation.record_id}.",
			record={"doctype": operation.doctype, "name": operation.record_id},
			before=before,
		)
	except Exception as error:
		frappe.db.rollback()
		return failed_sync_result(operation, error)


def sync_run_report(operation):
	import frappe
	from frappe.desk.query_report import run as run_report

	try:
		if not frappe.db.exists("Report", operation.report_name):
			raise ValueError(f"Unknown report: {operation.report_name}")
		output = run_report(operation.report_name, filters=operation.filters)
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Ran report {operation.report_name}.",
			output=_json_safe(output),
		)
	except Exception as error:
		return failed_sync_result(operation, error)


def sync_refresh_dashboard(operation):
	import frappe

	try:
		if not frappe.db.exists("Dashboard", operation.dashboard_name):
			raise ValueError(f"Unknown dashboard: {operation.dashboard_name}")
		dashboard = frappe.get_doc("Dashboard", operation.dashboard_name)
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Loaded dashboard {operation.dashboard_name} for refresh.",
			record={"doctype": "Dashboard", "name": operation.dashboard_name},
			output=_json_safe(dashboard.as_dict()),
		)
	except Exception as error:
		return failed_sync_result(operation, error)


def sync_run_scheduler(operation):
	import frappe

	try:
		method = operation.scheduler_name
		if not method.startswith("kratium."):
			raise ValueError("Scheduler operations are limited to kratium methods.")
		output = frappe.get_attr(method)(**operation.parameters)
		frappe.db.commit()
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Ran scheduler method {method}.",
			output=_json_safe(output),
		)
	except Exception as error:
		frappe.db.rollback()
		return failed_sync_result(operation, error)


def sync_send_notification(operation):
	try:
		return AtomicSyncResult(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			status="success",
			message=f"Prepared {operation.channel} notification.",
			output={
				"channel": operation.channel,
				"message": operation.message,
				"payload": _json_safe(operation.payload),
			},
		)
	except Exception as error:
		return failed_sync_result(operation, error)


def sync_external_call(operation):
	return AtomicSyncResult(
		operation_id=operation.operation_id,
		operation_type=operation.operation_type,
		operation_family=operation.operation_family,
		status="failed",
		message="External calls are not enabled for syncing yet.",
		error="External sync requires an integration allowlist before execution.",
	)


def validate_stale_record(operation, current_modified):
	if not expected_modified_matches(current_modified, operation.expected_modified):
		raise ValueError(
			f"Stale record for {operation.operation_id}: expected modified {operation.expected_modified}, current modified {current_modified}."
		)


def coerce_operation_fields_for_sync(doctype, fields):
	meta = _get_sync_meta(doctype)
	fieldtype_by_name = {field.fieldname: field.fieldtype for field in meta.fields}
	coerced = {}
	for fieldname, value in fields.items():
		fieldtype = fieldtype_by_name.get(fieldname)
		if fieldtype in {"Datetime", "Date", "Time"} and value is not None:
			coerced[fieldname] = coerce_datetime_for_frappe(value) if fieldtype in {"Datetime", "Date"} else value
		else:
			coerced[fieldname] = value
	return coerced


def coerce_datetime_for_frappe(value):
	value = _coerce_datetime(value)
	if value and value.tzinfo:
		value = value.astimezone(_local_timezone()).replace(tzinfo=None)
	return value


def failed_sync_result(operation, error):
	return AtomicSyncResult(
		operation_id=operation.operation_id,
		operation_type=operation.operation_type,
		operation_family=operation.operation_family,
		status="failed",
		message=f"Failed to sync {operation.operation_id}.",
		error=str(error),
	)


def build_execution_security_review(plan):
	plan = ExecutionPlan.model_validate(plan)
	evaluations = [evaluate_operation_security(plan, operation) for operation in plan.operations]
	prompts = group_execution_approvals(evaluations)
	queue = build_execution_queue(plan.operations, evaluations, prompts)
	blocked_reasons = [reason for evaluation in evaluations for reason in evaluation.blocking_reasons]
	overall_score = max([evaluation.risk_score for evaluation in evaluations] or [0])
	if prompts:
		overall_score = max(overall_score, max(prompt.risk_score for prompt in prompts))
	overall_risk = risk_level_from_score(overall_score)
	status = "blocked" if blocked_reasons else "waiting_for_approval" if prompts else "ready_to_execute"

	return ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status=status,
		overall_risk_level=overall_risk,
		overall_risk_score=overall_score,
		operation_evaluations=evaluations,
		approval_prompts=prompts,
		queue=queue,
		blocked_reasons=blocked_reasons,
	)


def run_execution_security_agent(plan):
	plan = ExecutionPlan.model_validate(plan)
	evaluations = [evaluate_operation_security(plan, operation) for operation in plan.operations]
	if should_use_deterministic_security_review(plan, evaluations):
		return build_execution_security_review_from_evaluations(plan, evaluations)
	prompt = build_execution_security_prompt(plan, evaluations)
	try:
		result = _run_agent_sync_with_retry(
			get_execution_security_agent(),
			prompt=prompt,
			deps=plan,
			conversation_id=f"execution-security-{plan.plan_id}",
		)
		return normalize_execution_security_review(plan, result.output, evaluations)
	except Exception as error:
		if not isinstance(error, (UnexpectedModelBehavior, UsageLimitExceeded)) and not _is_temporary_ai_provider_error(error):
			raise
		logfire.warning(
			"execution security agent unavailable; using deterministic security review",
			plan_id=plan.plan_id,
			error=str(error),
		)
		return build_execution_security_review_from_evaluations(plan, evaluations)


def should_use_deterministic_security_review(plan, evaluations):
	if len(plan.operations) > 5:
		return True
	return any(evaluation.operation_type == "doctype.delete" for evaluation in evaluations)


def normalize_execution_security_review(plan, review, evaluations):
	plan = ExecutionPlan.model_validate(plan)
	review = ExecutionSecurityReview.model_validate(review)
	evaluation_by_id = {evaluation.operation_id: evaluation for evaluation in evaluations}
	normalized_prompts = [
		normalize_execution_approval_prompt(prompt, evaluation_by_id)
		for prompt in review.approval_prompts
	]
	queue = build_execution_queue(plan.operations, evaluations, normalized_prompts)
	blocked_reasons = [reason for evaluation in evaluations for reason in evaluation.blocking_reasons]
	overall_score = max([evaluation.risk_score for evaluation in evaluations] or [0])
	if normalized_prompts:
		overall_score = max(overall_score, max(prompt.risk_score for prompt in normalized_prompts))
	status = "blocked" if blocked_reasons else "waiting_for_approval" if normalized_prompts else "ready_to_execute"
	return ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status=status,
		overall_risk_level=risk_level_from_score(overall_score),
		overall_risk_score=overall_score,
		operation_evaluations=evaluations,
		approval_prompts=normalized_prompts,
		queue=queue,
		blocked_reasons=blocked_reasons,
	)


def normalize_execution_approval_prompt(prompt, evaluation_by_id):
	prompt_evaluations = [
		evaluation_by_id[operation_id]
		for operation_id in prompt.operation_ids
		if operation_id in evaluation_by_id
	]
	if not prompt_evaluations:
		return prompt
	base_score = max(evaluation.risk_score for evaluation in prompt_evaluations)
	risk_score = max(prompt.risk_score, adjust_group_risk_score(base_score, prompt_evaluations))
	risk_level = risk_level_from_score(risk_score)
	explicit_confirmation = (
		prompt.explicit_confirmation_required
		or any(evaluation.explicit_confirmation_required for evaluation in prompt_evaluations)
		or risk_level in {"high", "critical"}
	)
	title = build_group_title(prompt.group_key, prompt_evaluations)
	confirmation_phrase = build_confirmation_phrase(prompt_evaluations, risk_level) if explicit_confirmation else None

	return ExecutionApprovalPrompt(
		group_id=prompt.group_id,
		group_key=prompt.group_key,
		title=title,
		operation_ids=prompt.operation_ids,
		risk_level=risk_level,
		risk_score=risk_score,
		permission_types=sorted({evaluation.permission_type for evaluation in prompt_evaluations if evaluation.permission_type}),
		prompt=build_group_prompt_text(title, prompt_evaluations, risk_level),
		reasons=sorted({*prompt.reasons, *[reason for evaluation in prompt_evaluations for reason in evaluation.reasons]}),
		explicit_confirmation_required=explicit_confirmation,
		confirmation_phrase=confirmation_phrase,
	)


def build_execution_security_review_from_evaluations(plan, evaluations):
	prompts = group_execution_approvals(evaluations)
	queue = build_execution_queue(plan.operations, evaluations, prompts)
	blocked_reasons = [reason for evaluation in evaluations for reason in evaluation.blocking_reasons]
	overall_score = max([evaluation.risk_score for evaluation in evaluations] or [0])
	if prompts:
		overall_score = max(overall_score, max(prompt.risk_score for prompt in prompts))
	return ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status="blocked" if blocked_reasons else "waiting_for_approval" if prompts else "ready_to_execute",
		overall_risk_level=risk_level_from_score(overall_score),
		overall_risk_score=overall_score,
		operation_evaluations=evaluations,
		approval_prompts=prompts,
		queue=queue,
		blocked_reasons=blocked_reasons,
	)


def build_execution_security_prompt(plan, evaluations):
	return (
		f"Execution plan summary:\n{summarize_security_plan(plan)}"
		f"\n\nDeterministic operation security facts:\n{to_jsonable_python([evaluation.model_dump() for evaluation in evaluations])}"
		"\n\nCreate the final ExecutionSecurityReview. Group approvals intelligently, but do not drop operations."
	)


def summarize_security_plan(plan):
	return {
		"plan_id": plan.plan_id,
		"goal": plan.problem.goal,
		"chosen_route_id": plan.chosen_route_id,
		"operation_count": len(plan.operations),
		"operations": [summarize_execution_operation(operation) for operation in plan.operations],
		"success_criteria": [criterion.model_dump() for criterion in plan.success_criteria],
	}


def evaluate_operation_security(plan, operation):
	if isinstance(operation, (CreateRecord, UpdateRecord, DeleteRecord)):
		return evaluate_doctype_operation_security(plan, operation)
	return evaluate_non_doctype_operation_security(operation)


def evaluate_doctype_operation_security(plan, operation):
	permission_type = doctype_permission_type(operation)
	permission_allowed, permission_reason = check_operation_permission(operation, permission_type)
	record_snapshot, record_reasons, stale_reasons = inspect_operation_record_state(operation)
	risk_score, reasons, explicit_confirmation = score_doctype_operation_risk(operation, record_snapshot)
	blocking_reasons = []
	if not permission_allowed:
		blocking_reasons.append(permission_reason)
	blocking_reasons.extend(stale_reasons)
	reasons.extend(record_reasons)
	if permission_reason and permission_allowed:
		reasons.append(permission_reason)

	return OperationSecurityEvaluation(
		operation_id=operation.operation_id,
		operation_type=operation.operation_type,
		operation_family=operation.operation_family,
		security_group_key=security_group_key_for_operation(operation, risk_score, record_snapshot),
		permission_type=permission_type,
		permission_allowed=permission_allowed,
		risk_level=risk_level_from_score(risk_score),
		risk_score=risk_score,
		approval_required=True,
		explicit_confirmation_required=explicit_confirmation,
		reasons=reasons,
		blocking_reasons=blocking_reasons,
		record_snapshot=record_snapshot,
	)


def evaluate_non_doctype_operation_security(operation):
	risk_by_type = {
		"report.run": (0.15, False, "Running a report is read-oriented."),
		"dashboard.refresh": (0.15, False, "Refreshing a dashboard should not mutate business records."),
		"scheduler.run": (0.75, True, "Scheduler runs can trigger broad system changes."),
		"notification.send": (0.45, False, "Notifications send information outside the current flow."),
		"external.call": (0.8, True, "External calls can affect systems outside Kratium."),
	}
	risk_score, explicit_confirmation, reason = risk_by_type.get(operation.operation_type, (0.7, True, "Unknown operation type."))
	return OperationSecurityEvaluation(
		operation_id=operation.operation_id,
		operation_type=operation.operation_type,
		operation_family=operation.operation_family,
		security_group_key=f"{operation.operation_type}",
		permission_type=None,
		permission_allowed=True,
		risk_level=risk_level_from_score(risk_score),
		risk_score=risk_score,
		approval_required=risk_score >= 0.4,
		explicit_confirmation_required=explicit_confirmation,
		reasons=[reason],
	)


def doctype_permission_type(operation):
	if isinstance(operation, CreateRecord):
		return "create"
	if isinstance(operation, UpdateRecord):
		return "write"
	if isinstance(operation, DeleteRecord):
		return "delete"
	return None


def check_operation_permission(operation, permission_type):
	if not permission_type:
		return True, "No DocType permission check required."
	if isinstance(operation, (UpdateRecord, DeleteRecord)) and is_malformed_record_id(operation.record_id):
		return False, explain_malformed_record_id(operation) or f"Malformed record id for {operation.operation_id}."
	try:
		import frappe

		if isinstance(operation, CreateRecord):
			doc = frappe.new_doc(operation.doctype)
			doc.update(operation.fields)
		elif isinstance(operation, DeleteRecord) and not operation.record_id:
			if frappe.has_permission(operation.doctype, "delete"):
				return True, f"Current user has delete permission for {operation.doctype}; dependency target will be checked at sync time."
			return False, f"Current user does not have delete permission for {operation.doctype}."
		else:
			doc = frappe.get_doc(operation.doctype, operation.record_id)
		doc.check_permission(permission_type)
		return True, f"Current user has {permission_type} permission for {operation.doctype}."
	except Exception as error:
		return False, f"Current user does not have {permission_type} permission for {operation.doctype}: {error}"


def inspect_operation_record_state(operation):
	if not isinstance(operation, (UpdateRecord, DeleteRecord)):
		return None, [], []
	if isinstance(operation, DeleteRecord) and not operation.record_id:
		return None, ["Delete target will be resolved from a prior operation dependency at sync time."], []
	if is_malformed_record_id(operation.record_id):
		return None, [], [explain_malformed_record_id(operation) or f"Malformed record id for {operation.operation_id}."]

	reasons = []
	blocking_reasons = []
	try:
		import frappe

		doc = frappe.get_doc(operation.doctype, operation.record_id)
		data = doc.as_dict()
		snapshot = build_security_record_snapshot(operation.doctype, data)
		reasons.append(f"Existing {operation.doctype} record was found for mutation.")
		if not expected_modified_matches(data.get("modified"), operation.expected_modified):
			blocking_reasons.append(
				f"{operation.operation_id} is stale: expected modified {operation.expected_modified}, current modified {data.get('modified')}."
			)
		return snapshot, reasons, blocking_reasons
	except Exception as error:
		blocking_reasons.append(f"Could not inspect existing record for {operation.operation_id}: {error}")
		return None, reasons, blocking_reasons


def build_security_record_snapshot(doctype, data):
	if doctype == "Action":
		snapshot = {field: data.get(field) for field in _action_summary_fields() if field in data}
		snapshot["goal"] = data.get("goal")
		snapshot["basegoal"] = data.get("basegoal")
		snapshot["milestone"] = data.get("milestone")
		snapshot["child_count"] = count_child_actions(data.get("name"))
		return _json_safe(snapshot)
	return _json_safe({"name": data.get("name"), "modified": data.get("modified")})


def count_child_actions(action_id):
	if not action_id:
		return 0
	try:
		import frappe

		return frappe.db.count("Action", {"parent_action": action_id})
	except Exception:
		return 0


def expected_modified_matches(current_modified, expected_modified):
	current = _coerce_datetime(current_modified)
	expected = _coerce_datetime(expected_modified)
	if not current or not expected:
		return False
	return abs((current - expected).total_seconds()) < 1


def score_doctype_operation_risk(operation, record_snapshot):
	reasons = []
	explicit_confirmation = False

	if isinstance(operation, CreateRecord):
		risk_score = 0.25
		reasons.append(f"Creates one {operation.doctype} record.")
		if operation.doctype == "Action" and operation.fields.get("event"):
			reasons.append("Creates a calendar-visible Action event.")
		if operation.doctype == "Action" and any(operation.fields.get(field) for field in ("goal", "basegoal", "is_group")):
			risk_score = max(risk_score, 0.45)
			reasons.append("Creates a planning or hierarchy Action, which has broader meaning than a simple event.")
	elif isinstance(operation, UpdateRecord):
		risk_score = 0.45
		reasons.append(f"Updates one existing {operation.doctype} record.")
		important_fields = set(operation.fields) & {"parent_action", "ancestor", "category", "start_date", "end_date", "status", "completed"}
		if important_fields:
			risk_score = max(risk_score, 0.55)
			reasons.append(f"Changes important scheduling/classification fields: {sorted(important_fields)}.")
	else:
		risk_score = 0.8
		explicit_confirmation = True
		reasons.append(f"Deletes one existing {operation.doctype} record.")

	if operation.doctype == "Action" and record_snapshot:
		if record_snapshot.get("is_group") or record_snapshot.get("goal") or record_snapshot.get("basegoal"):
			risk_score = max(risk_score, 0.95)
			explicit_confirmation = True
			reasons.append("Target Action is a group or goal-level record.")
		if record_snapshot.get("child_count", 0) > 0:
			risk_score = max(risk_score, 0.95)
			explicit_confirmation = True
			reasons.append("Target Action has child actions.")

	return risk_score, reasons, explicit_confirmation


def security_group_key_for_operation(operation, risk_score, record_snapshot=None):
	if isinstance(operation, DeleteRecord) and risk_score >= 0.9:
		return f"critical:{operation.operation_type}:{operation.doctype}:{operation.operation_id}"
	if isinstance(operation, (CreateRecord, UpdateRecord, DeleteRecord)):
		return f"{operation.operation_type}:{operation.doctype}"
	return operation.operation_type


def group_execution_approvals(evaluations):
	groups = {}
	for evaluation in evaluations:
		if evaluation.blocking_reasons or not evaluation.approval_required:
			continue
		groups.setdefault(evaluation.security_group_key, []).append(evaluation)

	prompts = []
	for index, (group_key, group_evaluations) in enumerate(groups.items(), start=1):
		prompt = build_group_approval_prompt(group_key, group_evaluations, index)
		prompts.append(prompt)
	return prompts


def build_group_approval_prompt(group_key, evaluations, index):
	operation_ids = [evaluation.operation_id for evaluation in evaluations]
	base_score = max(evaluation.risk_score for evaluation in evaluations)
	risk_score = adjust_group_risk_score(base_score, evaluations)
	risk_level = risk_level_from_score(risk_score)
	permission_types = sorted({evaluation.permission_type for evaluation in evaluations if evaluation.permission_type})
	explicit_confirmation = any(evaluation.explicit_confirmation_required for evaluation in evaluations) or risk_level in {"high", "critical"}
	title = build_group_title(group_key, evaluations)
	confirmation_phrase = None
	if explicit_confirmation:
		confirmation_phrase = build_confirmation_phrase(evaluations, risk_level)

	return ExecutionApprovalPrompt(
		group_id=f"security_group_{index}",
		group_key=group_key,
		title=title,
		operation_ids=operation_ids,
		risk_level=risk_level,
		risk_score=risk_score,
		permission_types=permission_types,
		prompt=build_group_prompt_text(title, evaluations, risk_level),
		reasons=sorted({reason for evaluation in evaluations for reason in evaluation.reasons}),
		explicit_confirmation_required=explicit_confirmation,
		confirmation_phrase=confirmation_phrase,
	)


def build_group_title(group_key, evaluations):
	first = evaluations[0]
	count = len(evaluations)
	if first.operation_type.startswith("doctype."):
		doctype = group_key.split(":")[1] if ":" in group_key else "record"
		verb = first.operation_type.split(".")[1]
		return f"Approve {count} {doctype} {verb} operation{'s' if count != 1 else ''}"
	return f"Approve {count} {first.operation_type} operation{'s' if count != 1 else ''}"


def build_group_prompt_text(title, evaluations, risk_level):
	operation_count = len(evaluations)
	operation_ids = ", ".join(evaluation.operation_id for evaluation in evaluations[:10])
	if operation_count > 10:
		operation_ids += f", and {operation_count - 10} more"
	return (
		f"{title}. This approval covers {operation_count} atomic operation"
		f"{'s' if operation_count != 1 else ''} with overall {risk_level} risk. "
		f"Operation IDs: {operation_ids}."
	)


def build_confirmation_phrase(evaluations, risk_level):
	operation_types = {evaluation.operation_type for evaluation in evaluations}
	if operation_types == {"doctype.delete"}:
		return f"I approve deleting {len(evaluations)} record{'s' if len(evaluations) != 1 else ''}"
	return f"I approve {len(evaluations)} {risk_level} risk operation{'s' if len(evaluations) != 1 else ''}"


def adjust_group_risk_score(base_score, evaluations):
	count = len(evaluations)
	operation_types = {evaluation.operation_type for evaluation in evaluations}
	risk_score = base_score
	if count >= 10:
		risk_score = max(risk_score, 0.7)
	if count >= 25:
		risk_score = max(risk_score, 0.9)
	if "doctype.delete" in operation_types and count > 1:
		risk_score = max(risk_score, 0.85)
	return min(risk_score, 1.0)


def build_execution_queue(operations, evaluations, prompts):
	evaluation_by_id = {evaluation.operation_id: evaluation for evaluation in evaluations}
	group_by_operation = {
		operation_id: prompt.group_id
		for prompt in prompts
		for operation_id in prompt.operation_ids
	}
	queue = []
	for position, operation in enumerate(operations, start=1):
		evaluation = evaluation_by_id[operation.operation_id]
		queue.append(ExecutionQueueItem(
			position=position,
			operation_id=operation.operation_id,
			security_group_id=group_by_operation.get(operation.operation_id),
			blocked=bool(evaluation.blocking_reasons),
			blocking_reasons=evaluation.blocking_reasons,
		))
	return queue


def risk_level_from_score(score):
	if score >= 0.9:
		return "critical"
	if score >= 0.7:
		return "high"
	if score >= 0.4:
		return "medium"
	return "low"


def preview_execution_security(final_input):
	state = None
	try:
		result = run_preview_orchestration_pipeline(final_input)
	except Exception as error:
		state = build_preview_orchestration_state(final_input)
		if _is_temporary_ai_provider_error(error):
			result = _network_pause_result(state, error)
		elif isinstance(error, UsageLimitExceeded):
			result = _usage_limit_pause_result(state, error)
		elif isinstance(error, UnexpectedModelBehavior):
			result = _model_behavior_pause_result(state, error)
		else:
			raise
	if isinstance(result.output, ExecutionPlan):
		normalized_plan = normalize_execution_plan_for_security(result.output)
		if normalized_plan != result.output:
			result.state.execution_plan = normalized_plan
			result = OrchestrationRunResult(output=normalized_plan, state=result.state)
	remember_orchestration_result(result)
	if not isinstance(result.output, ExecutionPlan):
		return {
			"orchestration": summarize_orchestration_result(result),
			"security_preparation": None,
		}
	remember_execution_plan(result.output)
	preparation = remember_execution_preparation(prepare_execution(result.output))
	return {
		"orchestration": summarize_orchestration_result(result),
		"security_preparation": summarize_execution_preparation(preparation),
	}


def preview_execution_security_compact(final_input):
	"""Return a compact execution/security preview for large-plan validation."""
	preview = preview_execution_security(final_input)
	orchestration = preview.get("orchestration") or {}
	security = preview.get("security_preparation") or {}
	operation_count = orchestration.get("operation_count")
	operations = orchestration.get("operations") or []
	return {
		"stage": orchestration.get("stage"),
		"status": orchestration.get("status"),
		"plan_id": orchestration.get("plan_id"),
		"operation_count": operation_count,
		"chosen_route_id": orchestration.get("chosen_route_id"),
		"first_operations": operations[:5],
		"last_operations": operations[-5:] if operations else [],
		"security_status": security.get("status"),
		"overall_risk_level": security.get("overall_risk_level"),
		"approval_prompt_count": len(security.get("approval_prompts") or []),
		"blocked_reasons": security.get("blocked_reasons") or [],
	}


def _model_behavior_pause_result(state, error):
	if is_broad_destructive_request(state.input.input):
		reason = (
			"The request is broad and destructive, so the AI could not safely produce a deterministic route. "
			"Narrow the delete target, date range, category, or exact records before execution. "
			f"Error: {error}"
		)
	else:
		reason = (
			"The AI stage could not produce a valid schema after retries. "
			"No system records were changed. This usually means the request exposed a missing schema pattern or validator rule. "
			f"Error: {error}"
		)
	return OrchestrationRunResult(
		output=OrchestrationPaused(
			stage=state.stage,
			required_tool=_required_tool_for_stage(state.stage),
			reason=reason,
		),
		state=state,
	)


def deterministic_information_answer_for_supported_request(final_input):
	text = final_input if isinstance(final_input, str) else getattr(final_input, "input", "")
	lower_text = (text or "").lower()
	if not is_read_only_information_request(lower_text):
		return None
	return InformationAnswer(results=[InformationResult(
		request_id="deterministic_read_only_preview",
		status="partial",
		answer="This request was recognized as read-only, but no deterministic local answer is available without running the information agent.",
		requested_output="Read-only information answer",
		strategy=["classified request as read-only", "left detailed answering to information collection when needed"],
		facts=[Evidence(source="system", reference="deterministic read-only classifier", fact="No system records were mutated.")],
		missing_information=["Detailed answer requires the information collection stage."],
		confidence=0.55,
	)])


def is_read_only_information_request(lower_text):
	if any(term in lower_text for term in ("create", "add", "make", "update", "change", "delete", "remove", "sync")):
		return False
	return any(term in lower_text for term in ("show", "list", "search", "find", "what", "which", "how many", "count", "check"))


def run_preview_orchestration_pipeline(final_input):
	information_answer = deterministic_information_answer_for_supported_request(final_input)
	if information_answer:
		state = build_preview_orchestration_state(final_input)
		state.information = information_answer.results
		state.stage = "complete"
		return OrchestrationRunResult(output=information_answer, state=state)

	fallback_plan = deterministic_execution_plan_for_supported_request(final_input)
	if fallback_plan:
		state = build_preview_orchestration_state(final_input)
		state.clarification = ClarificationResult(
			problem=fallback_plan.problem,
			evidence=[Evidence(source="system", reference="deterministic preview fallback", fact="A supported counted Action request was converted into concrete execution operations.")],
			confidence=0.86,
		)
		state.route_selection = RouteSelection(
			routes=fallback_plan.routes_considered,
			chosen_route_id=fallback_plan.chosen_route_id,
			decisions=fallback_plan.decisions[:1],
		)
		state.execution_plan = fallback_plan
		state.stage = "execution"
		return OrchestrationRunResult(output=fallback_plan, state=state)

	state = build_preview_orchestration_state(final_input)
	clarification = run_preview_clarification_stage(state)
	if isinstance(clarification, UserClarification):
		return OrchestrationRunResult(output=clarification, state=state)

	route_selection = run_preview_route_selection_stage(state)
	if isinstance(route_selection, UserClarification):
		return OrchestrationRunResult(output=route_selection, state=state)

	implementation = run_preview_implementation_stage(state)
	return OrchestrationRunResult(output=implementation, state=state)


def build_preview_orchestration_state(final_input):
	if isinstance(final_input, str):
		final_input = OrchestrationInput(input=final_input, source="direct")
	else:
		final_input = OrchestrationInput.model_validate(final_input)
	return OrchestrationState(
		orchestration_id=str(uuid4()),
		stage="clarification",
		input=final_input,
	)


def deterministic_execution_plan_for_supported_request(final_input):
	text = final_input if isinstance(final_input, str) else getattr(final_input, "input", "")
	if not should_use_deterministic_create_delete_action_plan(text):
		return None
	return build_deterministic_create_delete_action_plan(text)


def should_use_deterministic_create_delete_action_plan(text):
	"""Use deterministic fallback only where no record lookup is needed."""
	lower_text = (text or "").lower()
	if not any(term in lower_text for term in ("action", "actions", "todo", "todos")):
		return False
	if not any(term in lower_text for term in ("create", "add", "make")):
		return False
	if not extract_count_before_terms(lower_text, ("create", "add", "make")):
		return False
	if any(term in lower_text for term in ("delete", "remove")):
		return False
	return not should_use_action_blueprint_implementation(text)


def should_use_action_blueprint_implementation(text):
	"""Route broad Action-building requests to the blueprint station, not one-shot operations."""
	lower_text = (text or "").lower()
	if not any(term in lower_text for term in ("action", "todo", "routine", "regime", "plan", "schedule", "workout", "study", "subject", "template")):
		return False
	if is_read_only_information_request(lower_text):
		return False
	blueprint_terms = (
		"routine",
		"regime",
		"study",
		"workout",
		"template",
		"tree",
		"hierarchy",
		"under",
		"parent",
		"child",
		"children",
		"period",
		"schedule",
		"daily",
		"weekly",
		"subject",
		"subjects",
		"milestone",
		"focus",
	)
	if any(term in lower_text for term in blueprint_terms):
		return True
	create_count = extract_count_before_terms(lower_text, ("create", "add", "make")) or 0
	return create_count >= 15


def extract_count_before_terms(text, terms):
	lower_text = (text or "").lower()
	for term in terms:
		match = re.search(rf"(?:{term})\s+(\d+)\b|\b(\d+)\s+\w*\s*{term}", lower_text)
		if match:
			return int(next(group for group in match.groups() if group))
	return None


def build_deterministic_create_delete_action_plan(text):
	create_count = extract_count_before_terms(text, ("create", "add", "make")) or 1
	decision = Decision(
		decision_id="deterministic_counted_action_create_decision",
		question="Can the simple counted Action creation request be represented as atomic operations?",
		conclusion=f"Create {create_count} Action record(s).",
		alternatives=["Use the AI blueprint station for structured or broad designs."],
		evidence=[Evidence(source="system", reference="deterministic counted create fallback", fact="The request contains an explicit create count for Action records and no lookup-dependent mutation.")],
		confidence=0.84,
	)
	operations = []
	for index in range(create_count):
		operations.append(CreateRecord(
			operation_id=f"create_random_action_{index + 1:03d}",
			decision_id=decision.decision_id,
			description=f"Create random Action {index + 1} of {create_count}.",
			doctype="Action",
			fields={
				"action_name": f"Random Action {index + 1}",
				"description": "Generated by deterministic counted Action fallback.",
				"status": "Upcoming",
				"todo": True,
				"event": False,
			},
		))
	return ExecutionPlan(
		plan_id=str(uuid4()),
		problem=ProblemBreakdown(
			goal=text,
			assumptions=["No structured design language detected, so deterministic create fallback is allowed."],
		),
		routes_considered=[RouteOption(
			route_id="deterministic_counted_action_batch",
			outcome_type="create",
			description="Compile explicit counted Action create/delete request into atomic execution operations.",
			expected_outcome="Execution bus evaluates and syncs each atomic operation.",
			system_objects=["Action"],
			evidence=[Evidence(source="system", reference="deterministic counted batch fallback", fact="Explicit operation counts were found in the request.")],
			missing_information=[],
			reversibility="low",
			risks=["Delete operations are destructive and require security review."],
			confidence=0.84,
			score=0.84,
		)],
		chosen_route_id="deterministic_counted_action_batch",
		decisions=[decision],
		operations=operations,
		success_criteria=[SuccessCriterion(
			description="Verify counted Action create operations were attempted.",
			check="Compare executed operation count to requested create count.",
			expected_result=f"{create_count} operation(s) attempted with per-operation results.",
		)],
	)


def build_action_blueprint_execution_plan_for_request(text):
	"""Fallback Action implementation path when the model blueprint station is unavailable."""
	if not should_use_action_blueprint_implementation(text):
		return None
	return None


def should_use_action_blueprint_station(state):
	text = state.input.input if state and state.input else ""
	if not should_use_action_blueprint_implementation(text):
		return False
	if not state.route_selection:
		return False
	chosen_route = next(route for route in state.route_selection.routes if route.route_id == state.route_selection.chosen_route_id)
	return chosen_route.outcome_type in {"create", "plan", "monitor"}


def build_action_blueprint_prompt(state, chosen_route):
	return (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nClarification:\n{state.clarification.model_dump_json()}"
		f"\n\nChosen route:\n{chosen_route.model_dump_json()}"
		f"\n\nRoute selection:\n{state.route_selection.model_dump_json()}"
		f"\n\nCurrent datetime:\n{_now().isoformat()}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		"\n\nDesign a compact ActionImplementationBlueprint. "
		"Do not emit execution operations. The compiler will expand groups/templates into atomic Action creates. "
		"The Design information map inside the input is an implementation contract. Preserve every "
		"implementation_requirements item in blueprint groups, templates, variables, assumptions, or notes. "
		"Do not flatten structure, timing, naming, template, relationship, or field requirements into a generic parent. "
		"Use variable names that come from the map requirements and user answers rather than fixed domain examples."
	)


def action_implementation_design_from_blueprint(text, blueprint):
	blueprint = normalize_action_blueprint_from_information_map(text, blueprint)
	compiled_blueprint = expand_action_implementation_blueprint(text, blueprint)
	plan = compile_expanded_blueprint_to_execution_plan(text, compiled_blueprint)
	return ImplementationDesign(
		decisions=plan.decisions,
		operations=plan.operations,
		success_criteria=plan.success_criteria,
	)


def expand_action_implementation_blueprint(text, blueprint):
	"""Expand blueprint groups/templates into concrete Action blueprint items."""
	blueprint = ActionImplementationBlueprint.model_validate(blueprint)
	now = _now()
	items = []
	group_operation_ids = {}
	for index, group in enumerate(blueprint.groups, start=1):
		operation_id = safe_operation_id(f"group_{group.group_id}")
		group_operation_ids[group.group_id] = operation_id
		parent_operation_id = group_operation_ids.get(group.parent_group_id)
		start_date = now + timedelta(days=max(0, index - 1))
		end_date = start_date + timedelta(days=max(1, group.estimated_days))
		items.append(ActionBlueprintItem(
			operation_id=operation_id,
			action_name=group.name,
			description=group.description,
			start_date=start_date,
			end_date=end_date,
			is_group=True,
			todo=False,
			event=False,
			parent_operation_id=parent_operation_id,
			status="Upcoming",
		))
	for template in blueprint.templates:
		items.extend(expand_action_blueprint_template(template, group_operation_ids, now))
	if not items:
		items.append(ActionBlueprintItem(
			operation_id="create_action_blueprint_root",
			action_name=blueprint.title,
			description="Generated Action structure root.",
			start_date=now,
			end_date=now + timedelta(hours=1),
			is_group=True,
			todo=False,
			event=False,
			status="Upcoming",
		))
	return ActionPlanBlueprint(
		domain=blueprint.domain,
		target_action_count=blueprint.target_action_count,
		items=items[:blueprint.target_action_count],
		assumptions=list(blueprint.assumptions or []) + list(blueprint.implementation_notes or []),
		source="ai_action_implementation_blueprint",
	)


def expand_action_blueprint_template(template, group_operation_ids, base_datetime):
	"""Expand one repeated template using variable combinations and count."""
	variables = template.variables or {}
	combinations = variable_combinations(variables)
	if not combinations:
		combinations = [{}]
	items = []
	parent_operation_id = group_operation_ids.get(template.parent_group_id)
	for index in range(template.count):
		values = dict(combinations[index % len(combinations)])
		values.setdefault("index", index + 1)
		values.setdefault("number", index + 1)
		name = render_action_template_text(template.name_pattern, values, fallback=f"{template.name_pattern} {index + 1}")
		description = render_action_template_text(template.description_pattern, values, fallback=template.description_pattern)
		start_date = base_datetime + timedelta(days=index)
		end_date = start_date + timedelta(minutes=template.duration_minutes)
		items.append(ActionBlueprintItem(
			operation_id=safe_operation_id(f"template_{template.template_id}_{index + 1:03d}"),
			action_name=name,
			description=description,
			start_date=start_date,
			end_date=end_date,
			is_group=False,
			todo=template.todo,
			event=template.event,
			parent_operation_id=parent_operation_id,
			status="Upcoming",
		))
	return items


def variable_combinations(variables):
	"""Return deterministic variable rows for template expansion."""
	if not variables:
		return []
	keys = list(variables.keys())
	max_length = max((len(values) for values in variables.values() if isinstance(values, list)), default=0)
	rows = []
	for index in range(max_length):
		row = {}
		for key in keys:
			values = variables.get(key) or []
			if values:
				row[key] = values[index % len(values)]
		rows.append(row)
	return rows


def render_action_template_text(pattern, values, fallback=""):
	"""Render a blueprint pattern without failing on missing variables."""
	try:
		return (pattern or fallback).format(**values)
	except Exception:
		return pattern or fallback


def safe_operation_id(value):
	"""Normalize blueprint IDs into execution-operation-safe identifiers."""
	operation_id = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "operation")).strip("_").lower()
	return operation_id or "operation"


def compile_expanded_blueprint_to_execution_plan(text, blueprint):
	"""Convert expanded Action blueprint items into atomic Action create operations."""
	blueprint = ActionPlanBlueprint.model_validate(blueprint)
	decision = Decision(
		decision_id="compile_action_blueprint_decision",
		question="How should the Action blueprint become executable operations?",
		conclusion="Create one Action record per expanded blueprint item, preserving parent operation references for hierarchy.",
		alternatives=["Ask for more clarification", "Use one flat generated Action list"],
		evidence=[Evidence(source="system", reference="Action blueprint compiler", fact=f"Expanded blueprint contains {len(blueprint.items)} Action item(s).")],
		confidence=0.86,
	)
	operations = []
	seen_ids = set()
	for item in blueprint.items:
		operation_id = unique_operation_id(item.operation_id, seen_ids)
		fields = {
			"action_name": item.action_name,
			"description": item.description,
			"start_date": item.start_date,
			"end_date": item.end_date,
			"status": item.status or "Upcoming",
			"todo": item.todo,
			"event": item.event,
			"is_group": item.is_group,
		}
		dependencies = []
		if item.parent_operation_id:
			parent_operation_id = safe_operation_id(item.parent_operation_id)
			fields["parent_action"] = parent_operation_id
			dependencies.append(OperationDependency(target="operation", operation_id=parent_operation_id))
		operations.append(CreateRecord(
			operation_id=operation_id,
			decision_id=decision.decision_id,
			description=f"Create Action '{item.action_name}'.",
			doctype="Action",
			fields=fields,
			dependencies=dependencies,
		))
	return ExecutionPlan(
		plan_id=str(uuid4()),
		problem=ProblemBreakdown(
			goal=text,
			assumptions=[*blueprint.assumptions, "Preserve blueprint hierarchy through same-plan operation dependencies."],
		),
		routes_considered=[RouteOption(
			route_id="compile_action_blueprint",
			outcome_type="create",
			description="Compile the Action blueprint into execution-bus create operations.",
			expected_outcome="The sync layer creates the Action tree and resolves same-plan parent links.",
			system_objects=["Action"],
			evidence=[Evidence(source="system", reference="Action blueprint compiler", fact=f"Compiled {len(operations)} Action operation(s).")],
			missing_information=[],
			reversibility="medium",
			risks=["Large create batches require security review before sync."],
			confidence=0.86,
			score=0.86,
		)],
		chosen_route_id="compile_action_blueprint",
		decisions=[decision],
		operations=operations,
		success_criteria=[SuccessCriterion(
			description="Verify all blueprint Action operations were attempted.",
			check="Compare execution report records to compiled operation IDs.",
			expected_result=f"{len(operations)} create operation(s) attempted with per-operation records.",
		)],
	)


def unique_operation_id(operation_id, seen_ids):
	base_id = safe_operation_id(operation_id)
	unique_id = base_id
	index = 2
	while unique_id in seen_ids:
		unique_id = f"{base_id}_{index}"
		index += 1
	seen_ids.add(unique_id)
	return unique_id


def normalize_action_blueprint_from_information_map(text, blueprint):
	blueprint = ActionImplementationBlueprint.model_validate(blueprint)
	map_data = extract_information_map_from_text(text)
	if not map_data:
		return blueprint
	requirements = [
		requirement for requirement in map_data.get("implementation_requirements") or []
		if requirement.get("must_preserve", True)
	]
	missing_requirements = [
		requirement for requirement in requirements
		if not blueprint_preserves_information_requirement(blueprint, requirement)
	]
	if not missing_requirements:
		return blueprint
	blueprint_dict = blueprint.model_dump()
	blueprint_dict["implementation_notes"] = list(blueprint_dict.get("implementation_notes") or [])
	for requirement in missing_requirements:
		blueprint_dict["implementation_notes"].append(
			f"Information-map requirement to preserve: {requirement.get('description')} Hint: {requirement.get('blueprint_hint', '')}"
		)
	return ActionImplementationBlueprint.model_validate(blueprint_dict)


def extract_information_map_from_text(text):
	marker = "Design information map:\n"
	if marker not in (text or ""):
		return None
	map_text = text.split(marker, 1)[1].split("\n\nProgressive design interview answers:", 1)[0]
	try:
		return json.loads(map_text)
	except Exception:
		return None



def infer_focus_cycle_from_text(text):
	lower_text = (text or "").lower()
	focuses = []
	for label, terms in {
		"Legs": ("legs", "leg"),
		"Cardio": ("cardio", "conditioning", "endurance"),
		"Upper Body": ("upper", "push", "pull", "arms", "chest", "back"),
		"Core": ("core", "abs"),
		"Mobility": ("mobility", "stretch", "recovery"),
	}.items():
		if any(term in lower_text for term in terms):
			focuses.append(label)
	if not focuses and any(term in lower_text for term in ("focus", "cycle", "cycling")):
		focuses = ["Legs", "Cardio", "Upper Body", "Core", "Mobility"]
	if not focuses:
		return None
	return {
		"focuses": focuses,
		"cadence_days": 2 if any(term in lower_text for term in ("every 2 days", "every two days", "2 days")) else None,
	}


def infer_schedule_pattern_from_text(text):
	lower_text = (text or "").lower()
	pattern = {}
	if "week" in lower_text:
		pattern["period"] = "week"
	if any(term in lower_text for term in ("every 2 days", "every two days", "2 days")):
		pattern["cadence"] = "rotate focus every 2 days"
	if "copy and paste" in lower_text:
		pattern["template_application"] = "copy template into each scheduled day/session"
	if any(term in lower_text for term in ("right time", "when each", "figure out when")):
		pattern["time_selection"] = "choose practical times from the mapped structure"
	return pattern or None


def build_design_field_intents(prompt, scope, answers, assumptions, unknowns):
	base_intents = [
		DesignFieldIntent(doctype="Action", fieldname="action_name", label="Name", value_strategy="assumed", value="generated_from_map", reason="Every Action needs a readable name; naming assumptions are tracked in the map.", confidence=0.82),
		DesignFieldIntent(doctype="Action", fieldname="description", label="Description", value_strategy="assumed", value="generated_from_scope_and_template", reason="Descriptions should explain the purpose of each generated Action.", confidence=0.78),
		DesignFieldIntent(doctype="Action", fieldname="start_date", label="Start Date", value_strategy="assumed", value="scheduled_by_blueprint", reason="Generated Actions need approximate timing; timing assumptions are mapped.", confidence=0.72),
		DesignFieldIntent(doctype="Action", fieldname="end_date", label="End Date", value_strategy="assumed", value="scheduled_by_blueprint", reason="End dates follow duration assumptions from the blueprint.", confidence=0.72),
		DesignFieldIntent(doctype="Action", fieldname="status", label="Status", value_strategy="assumed", value="Upcoming", reason="New planned Actions start as Upcoming.", confidence=0.86),
		DesignFieldIntent(doctype="Action", fieldname="todo", label="Todo", value_strategy="assumed", value="true_for_leaf_false_for_groups", reason="Concrete Actions should be executable todos while containers should not.", confidence=0.88),
		DesignFieldIntent(doctype="Action", fieldname="event", label="Event", value_strategy="assumed", value=False, reason="Generated structures are todos unless the prompt requests fixed calendar events.", confidence=0.84),
		DesignFieldIntent(doctype="Action", fieldname="is_group", label="Is Group", value_strategy="assumed", value="true_for_containers", reason="Hierarchy needs group/container Actions.", confidence=0.88),
		DesignFieldIntent(doctype="Action", fieldname="parent_action", label="Parent Action", value_strategy="assumed", value="operation_id_reference", reason="The sync layer resolves parent operation IDs into record names.", confidence=0.9),
	]
	return merge_doctype_field_intents("Action", base_intents, prompt, scope)


def merge_doctype_field_intents(doctype, base_intents, prompt, scope):
	intents_by_field = {intent.fieldname: intent for intent in base_intents}
	for field in get_design_map_doctype_fields(doctype):
		fieldname = field.get("fieldname")
		if not fieldname or fieldname in intents_by_field:
			continue
		strategy = design_field_strategy_for_field(field, prompt, scope)
		if strategy["value_strategy"] == "skip":
			continue
		intents_by_field[fieldname] = DesignFieldIntent(
			doctype=doctype,
			fieldname=fieldname,
			label=field.get("label"),
			value_strategy=strategy["value_strategy"],
			value=strategy.get("value"),
			reason=strategy["reason"],
			confidence=strategy["confidence"],
		)
	return list(intents_by_field.values())


def get_design_map_doctype_fields(doctype):
	try:
		import frappe

		meta = frappe.get_meta(doctype)
		return [
			{
				"fieldname": field.fieldname,
				"label": field.label,
				"fieldtype": field.fieldtype,
				"options": field.options,
				"required": bool(field.reqd),
				"read_only": bool(field.read_only),
				"default": field.default,
			}
			for field in meta.fields
			if field.fieldname and not field.read_only
		]
	except Exception:
		return []


def design_field_strategy_for_field(field, prompt, scope):
	fieldname = field.get("fieldname")
	fieldtype = field.get("fieldtype")
	label = (field.get("label") or fieldname or "").lower()
	lower_prompt = (prompt or "").lower()
	if field.get("required"):
		return {"value_strategy": "ask", "value": None, "reason": f"Required field {fieldname} must be resolved before sync if no default applies.", "confidence": 0.6}
	if fieldtype in {"Data", "Small Text", "Text", "Long Text"} and any(term in label for term in ("description", "name", "title")):
		return {"value_strategy": "assumed", "value": "generated_from_map", "reason": f"Text field {fieldname} can be filled from the information map.", "confidence": 0.68}
	if "calendar" in lower_prompt and fieldtype in {"Datetime", "Date"}:
		return {"value_strategy": "ask", "value": None, "reason": f"Calendar timing field {fieldname} may need user timing specifics.", "confidence": 0.62}
	return {"value_strategy": "skip", "reason": f"Field {fieldname} is not relevant enough for this map.", "confidence": 0.5}


def classify_design_scope(prompt, answers=None):
	lower_text = (prompt or "").lower()
	answers = answers or []
	answer_text = " ".join(str(answer.get("answer", "")) for answer in answers).lower()
	combined = f"{lower_text} {answer_text}"
	
	# Simple batch requests (create/delete N actions/todos) skip the interview.
	# They are not structured plans that need scope/detail/structure questions.
	if _is_simple_batch_request(lower_text):
		return {"scope_type": "simple_action", "domain": "generic", "likely_action_count_range": (1, 5)}
	
	domain = "generic"
	if any(term in combined for term in ("workout", "exercise", "gym")):
		domain = "workout"
	elif any(term in combined for term in ("study", "university", "subject", "test", "exam")):
		domain = "study"

	large_terms = {"entire", "regime", "system", "semester", "until", "tests", "subjects"}
	structured_terms = {"routine", "plan", "schedule", "program", "regime", "system", "under", "daily"}
	if domain == "study" and any(term in combined for term in large_terms):
		scope_type = "large_regime"
		return {"scope_type": scope_type, "domain": domain, "likely_action_count_range": estimate_design_scale(scope_type, domain, answers)}
	if domain == "workout" and any(term in combined for term in structured_terms):
		scope_type = "structured_plan"
		return {"scope_type": scope_type, "domain": domain, "likely_action_count_range": estimate_design_scale(scope_type, domain, answers)}
	if any(term in combined for term in structured_terms):
		scope_type = "generic_structured_plan"
		return {"scope_type": scope_type, "domain": domain, "likely_action_count_range": estimate_design_scale(scope_type, domain, answers)}
	scope_type = "simple_action"
	return {"scope_type": scope_type, "domain": domain, "likely_action_count_range": estimate_design_scale(scope_type, domain, answers)}



def _is_simple_batch_request(text):
	"""Detect simple create/delete N action/todo requests that should not trigger the design interview."""
	# Matches phrases like "create 10 actions", "delete 3 random actions", "create 5 then delete 2"
	has_number = bool(re.search(r"\b\d+\b", text))
	if not has_number:
		return False
	# Must be about actions/todos/calendar events
	if not any(term in text for term in ("action", "actions", "todo", "todos")):
		return False
	# Must have create/delete/add/remove
	if not any(verb in text for verb in ("create", "add", "make", "delete", "remove", "clear")):
		return False
	# Must NOT have structural words that indicate a structured plan
	structural_words = {"routine", "workout", "study", "regime", "schedule", "program", "daily", "under", "parent", "hierarchy", "structure"}
	if any(word in text for word in structural_words):
		return False
	# Must NOT have large-regime indicators
	regime_words = {"entire", "semester", "until", "subjects", "university"}
	if any(word in text for word in regime_words):
		return False
	return True


def extract_requested_action_count(text):
	match = re.search(r"\b(?:at\s+least|about|around|roughly|approximately)?\s*(\d{1,4})\s+(?:actions?|todos?|records?|items?)\b", text or "")
	if not match:
		return None
	return int(match.group(1))


def design_answer_for(answers, question_id, *, include_inferred=True):
	for answer in answers or []:
		if answer.get("question_id") == question_id:
			if not include_inferred and answer.get("inferred"):
				continue
			return str(answer.get("answer") or "")
	return ""


def design_answer_text(answers):
	return " ".join(str(answer.get("answer") or "") for answer in answers or []).lower()


def design_assumption_review_requested(prompt, answers=None):
	text = " ".join([prompt or "", design_answer_text(answers)]).lower()
	return any(phrase in text for phrase in (
		"ask about rest of the assumptions",
		"ask about the rest of the assumptions",
		"ask the rest of the assumptions",
		"ask about assumptions",
		"ask all assumptions",
		"ask me assumptions",
		"ask me the assumptions",
		"ask me the rest",
		"don't assume",
		"do not assume",
		"no assumptions",
		"let me decide assumptions",
		"review assumptions",
		"rest of the assumption",
		"rest of assumptions",
	))


def estimate_design_scale(scope_type, domain, answers=None):
	answers = answers or []
	answer_text = " ".join(str(answer.get("answer", "")) for answer in answers).lower()
	requested_count = extract_requested_action_count(answer_text)
	if requested_count:
		return (requested_count, max(requested_count, int(requested_count * 1.25)))
	if domain == "study":
		if "300" in answer_text:
			return (300, 420)
		if "150" in answer_text:
			return (150, 320)
		if "100" in answer_text:
			return (100, 220)
		if "50" in answer_text:
			return (50, 120)
		if "detailed daily" in answer_text:
			return (120, 300)
		if "lightweight" in answer_text:
			return (20, 60)
		return (50, 160) if scope_type == "large_regime" else (15, 60)
	if domain == "workout":
		if "exercise-by-exercise" in answer_text or "detailed" in answer_text:
			return (35, 120)
		if "simple" in answer_text:
			return (10, 30)
		return (20, 90)
	if scope_type == "generic_structured_plan":
		if "detailed" in answer_text:
			return (40, 120)
		if "lightweight" in answer_text:
			return (5, 25)
		return (10, 80)
	return (1, 5)


def infer_design_answers(prompt, scope, existing_answers=None):
	existing_answers = existing_answers or []
	answered = {answer.get("question_id") for answer in existing_answers}
	lower_prompt = (prompt or "").lower()
	inferred = []

	def add(question_id, phase, question, answer, reason, confidence=0.86):
		if question_id in answered:
			return
		inferred.append({
			"question_id": question_id,
			"phase": phase,
			"question": question,
			"answer": answer,
			"inferred": True,
			"confidence": confidence,
			"reason": reason,
		})

	if any(term in lower_prompt for term in ("until", "test", "tests", "exam", "exams", "writing tests")):
		add(
			"explicit_endpoint",
			"scope",
			"What endpoint should the generated system reach?",
			"Include the requested endpoint or milestone stage.",
			"The prompt explicitly describes the endpoint, so this can be carried into the map without another question.",
		)
	requested_count = extract_requested_action_count(lower_prompt)
	if requested_count:
		add(
			"explicit_requested_count",
			"extent",
			"How many Actions should be generated?",
			f"About {requested_count} Actions",
			"The prompt explicitly includes an Action count.",
		)
	if "random" in lower_prompt:
		add(
			"random_naming_allowed",
			"specifics",
			"May generated names be random?",
			"Use generated random names where the request says random.",
			"The prompt explicitly permits random generation.",
		)

	return inferred


def merge_design_answers(explicit_answers, inferred_answers):
	merged = list(explicit_answers or [])
	seen = {answer.get("question_id") for answer in merged}
	for answer in inferred_answers or []:
		if answer.get("question_id") not in seen:
			merged.append(answer)
			seen.add(answer.get("question_id"))
	return merged


def build_progressive_design_question_plan(prompt, answers=None):
	answers = answers or []
	scope = classify_design_scope(prompt, answers)
	inferred_answers = infer_design_answers(prompt, scope, answers)
	combined_answers = merge_design_answers(answers, inferred_answers)
	scope = classify_design_scope(prompt, combined_answers)
	scope["answers"] = combined_answers
	information_map = build_design_information_map(prompt, scope, combined_answers)
	planner_decision = run_design_question_planner(prompt, scope, combined_answers, information_map)
	information_map = apply_design_question_planner_decision(information_map, planner_decision)
	questions = [planner_decision.question] if planner_decision.status == "ask" and planner_decision.question else []
	return DesignQuestionPlan(
		scope_type=scope["scope_type"],
		domain=scope["domain"],
		likely_action_count_range=tuple(scope["likely_action_count_range"]),
		questions=questions,
		inferred_answers=inferred_answers,
		system_assumptions=build_system_assumptions_for_design(scope, combined_answers),
		information_map=information_map,
	)


def run_design_question_planner(prompt, scope, answers, information_map):
	"""Ask the AI planner whether the information map needs one more user answer."""
	if scope.get("scope_type") == "simple_action":
		return DesignQuestionPlannerDecision(
			status="ready",
			reasoning_summary="Simple action request does not need a design interview.",
			complexity_assessment="low",
			estimated_total_questions=0,
			dimension_reviews=[
				DesignMapDimensionReview(dimension="scope", status="resolved", impact="low", reason="Simple action request has direct scope."),
				DesignMapDimensionReview(dimension="scale", status="resolved", impact="low", reason="Simple action request has small scale."),
				DesignMapDimensionReview(dimension="structure", status="resolved", impact="low", reason="No broad structure is needed."),
				DesignMapDimensionReview(dimension="relationships", status="resolved", impact="low", reason="No relationship design is needed."),
				DesignMapDimensionReview(dimension="timing", status="assumed", impact="low", reason="Timing can be inferred by the implementation stage if relevant."),
				DesignMapDimensionReview(dimension="naming", status="assumed", impact="low", reason="Name can be inferred from the prompt."),
				DesignMapDimensionReview(dimension="content", status="resolved", impact="low", reason="Prompt content is sufficient for one action."),
				DesignMapDimensionReview(dimension="fields", status="assumed", impact="low", reason="Default Action field strategy is sufficient."),
				DesignMapDimensionReview(dimension="assumptions", status="assumed", impact="low", reason="Only low-impact defaults remain."),
			],
		)
	try:
		result = _run_agent_sync_with_retry(
			get_design_question_planner_agent(),
			prompt=build_design_question_planner_prompt(prompt, scope, answers, information_map),
			deps=None,
			conversation_id=str(uuid4()),
		)
	except Exception:
		return fallback_design_question_planner_decision(prompt, scope, answers, information_map)
	try:
		return enforce_design_question_planner_boundaries(prompt, scope, answers, information_map, result.output)
	except ModelRetry:
		return fallback_design_question_planner_decision(prompt, scope, answers, information_map)


def enforce_design_question_planner_boundaries(prompt, scope, answers, information_map, planner_decision):
	"""Validate planner output without deciding the interview for it."""
	planner_decision = DesignQuestionPlannerDecision.model_validate(planner_decision)
	if planner_decision.status == "ask":
		return planner_decision
	unresolved_reviews = [
		review
		for review in planner_decision.dimension_reviews
		if review.status == "needs_user" and review.impact in {"high", "critical"}
	]
	if unresolved_reviews:
		raise ModelRetry("Planner marked the map ready while high-impact dimensions still need the user.")
	if broad_design_scope(scope) and not planner_ready_has_core_dimension_coverage(planner_decision):
		raise ModelRetry(
			"Broad design maps need explicit dimension review coverage for scope/scale, structure/relationships, "
			"timing, naming, content, fields, and assumptions before status='ready'."
		)
	if broad_design_scope(scope) and weak_answers_for_broad_design(answers):
		raise ModelRetry(
			"A short answer without explicit delegation cannot complete a broad design map. Ask the next highest-impact question."
		)
	return planner_decision


def broad_design_scope(scope):
	return scope.get("scope_type") in {"structured_plan", "large_regime", "generic_structured_plan"}


def weak_answers_for_broad_design(answers):
	if not answers:
		return False
	answer_text = "\n".join(str(answer.get("answer") or "") for answer in answers if isinstance(answer, dict)).strip()
	word_count = len(re.findall(r"\w+", answer_text))
	delegation_terms = ("you decide", "decide for me", "make assumptions", "use your judgement", "figure out", "simple", "basic")
	return word_count <= 8 and not any(term in answer_text.lower() for term in delegation_terms)


def planner_ready_has_core_dimension_coverage(planner_decision):
	reviewed = {review.dimension for review in planner_decision.dimension_reviews}
	required_groups = [
		{"scope", "scale"},
		{"structure", "relationships"},
		{"timing"},
		{"naming"},
		{"content"},
		{"fields"},
		{"assumptions"},
	]
	return all(reviewed.intersection(group) for group in required_groups)


def planner_ready_relies_on_high_impact_assumptions(planner_decision):
	important_reviews = [review for review in planner_decision.dimension_reviews if review.impact in {"high", "critical"}]
	return any(review.status == "assumed" for review in important_reviews)


def design_question_shapes_implementation_map(question):
	if not question:
		return False
	text = f"{question.question_id} {question.question} {question.reason} {question.default_assumption or ''}".lower()
	return any(term in text for term in (
		"structure",
		"hierarchy",
		"tree",
		"parent",
		"child",
		"children",
		"level",
		"template",
		"instance",
		"period",
		"schedule",
		"timing",
		"scale",
		"count",
		"naming",
		"assumption",
	))


def build_design_question_planner_prompt(prompt, scope, answers, information_map):
	return (
		f"Original prompt:\n{prompt}"
		f"\n\nPrior user answers:\n{json.dumps(answers or [], default=str, indent=2)}"
		f"\n\nClassified scope:\n{json.dumps(scope, default=str, indent=2)}"
		f"\n\nCurrent information map:\n{information_map.model_dump_json(indent=2)}"
		"\n\nYou are the dynamic information-map planner, not a template question generator. "
		"There is no fixed question list and no fixed maximum question count. Ask as many or as few concise questions as the specific problem needs. "
		"Before declaring ready, review the map dimensions explicitly: scope/scale, structure and relationships, templates versus generated instances, timing/scheduling, naming/readability, content/detail, DocType fields, assumptions, and security separation. "
		"For each dimension, return a dimension_reviews item saying whether it is resolved by prompt/answers, safely assumed, explicitly delegated by the user, or still needs the user. "
		"If any high-impact dimension still needs the user, status must be ask and ready_blockers must name the blocker. "
		"A short answer like 'full body' usually resolves only one dimension; it must not make a broad design ready unless all other high-impact dimensions are resolved, safely assumed with reasons, or explicitly delegated. "
		"If asking, ask exactly one prompt-specific question that resolves the highest-value remaining map gaps. Bundle related assumptions into that one question when efficient, but do not use canned IDs or old checklist wording. "
		"If ready, explain the assumptions being made and which gaps those assumptions resolve. Security/permission questions are never asked here."
	)


def fallback_design_question_planner_decision(prompt, scope, answers, information_map):
	"""Provider-failure fallback: never declare broad design ready after one answer."""
	if broad_design_scope(scope) and weak_answers_for_broad_design(answers):
		return DesignQuestionPlannerDecision(
			status="ask",
			reasoning_summary="The previous answer only resolved a narrow part of a broad design map.",
			complexity_assessment="broad design still has unresolved implementation dimensions",
			estimated_total_questions=max(2, len(answers or []) + 1),
			ready_blockers=["Broad design still needs implementation-shaping details beyond the short answer."],
			question=DesignQuestion(
				question_id=f"dynamic_map_completion_{len(answers or []) + 1}",
				phase="structure",
				question="I have one design choice, but not enough to build the full structure well. What should I know about the schedule/period, parent-child tree, naming style, and level of detail before I generate the Actions?",
				reason="Broad designs need enough scope, structure, timing, naming, and detail to create a useful Action tree instead of guessing the whole system from one short answer.",
				options=[],
				default_assumption="If you want me to decide, say so and I will make the remaining assumptions explicitly.",
				required=True,
			),
		)
	question = first_structural_unknown_question(information_map)
	if question:
		return DesignQuestionPlannerDecision(
			status="ask",
			reasoning_summary="Fallback asks only the highest-impact unresolved structure question.",
			complexity_assessment="medium",
			estimated_total_questions=1,
			question=question,
		)
	return DesignQuestionPlannerDecision(
		status="ready",
		reasoning_summary="Fallback found no structural blocker.",
		complexity_assessment="low",
		estimated_total_questions=0,
		dimension_reviews=[
			DesignMapDimensionReview(dimension="scope", status="assumed", impact="medium", reason="Fallback could not reach the planner, and no structural unknown remained."),
			DesignMapDimensionReview(dimension="scale", status="assumed", impact="medium", reason="Fallback uses the existing information-map scale model."),
			DesignMapDimensionReview(dimension="structure", status="assumed", impact="medium", reason="Fallback uses the existing information-map structure model."),
			DesignMapDimensionReview(dimension="relationships", status="assumed", impact="medium", reason="Fallback uses existing relationship requirements."),
			DesignMapDimensionReview(dimension="timing", status="assumed", impact="medium", reason="Fallback uses existing timing assumptions."),
			DesignMapDimensionReview(dimension="naming", status="assumed", impact="medium", reason="Fallback uses existing naming assumptions."),
			DesignMapDimensionReview(dimension="content", status="assumed", impact="medium", reason="Fallback uses existing content assumptions."),
			DesignMapDimensionReview(dimension="fields", status="assumed", impact="medium", reason="Fallback uses existing field intents."),
			DesignMapDimensionReview(dimension="assumptions", status="assumed", impact="medium", reason="Fallback preserves already recorded assumptions."),
		],
	)


def first_structural_unknown_question(information_map):
	for unknown in information_map.unknowns:
		if unknown.category in {"structure", "scope", "doctype", "fields", "timing", "naming", "content"}:
			return DesignQuestion(
				question_id=f"dynamic_{unknown.unknown_id}",
				phase=design_question_phase_for_category(unknown.category),
				question=unknown.question,
				reason=unknown.reason,
				options=unknown.options,
				default_assumption=unknown.default_assumption,
				required=True,
			)
	return None


def apply_design_question_planner_decision(information_map, planner_decision):
	updates = {}
	assumptions = list(information_map.assumptions or [])
	assumptions.extend(planner_decision.assumptions_to_make or [])
	updates["assumptions"] = assumptions
	updates["readiness"] = "needs_question" if planner_decision.status == "ask" else "ready"
	updates["readiness_reason"] = planner_decision.reasoning_summary
	budget = dict(information_map.question_budget or {})
	budget["estimated_total_questions"] = planner_decision.estimated_total_questions
	budget["planner_complexity_assessment"] = planner_decision.complexity_assessment
	budget["planner_reasoning_summary"] = planner_decision.reasoning_summary
	budget["strategy"] = "ai_dynamic_question_planner"
	updates["question_budget"] = budget
	if planner_decision.status == "ready":
		updates["unknowns"] = [unknown.model_copy(update={"ask": False}) for unknown in information_map.unknowns]
	return information_map.model_copy(update=updates)


def build_design_information_map(prompt, scope, answers=None):
	answers = answers or []
	domain = scope["domain"]
	scope_type = scope["scope_type"]
	combined_answers = list(answers) + [{"question_id": "original_prompt", "answer": prompt}]
	likely_range = estimate_design_scale(scope_type, domain, combined_answers)
	question_budget = estimate_design_question_budget(prompt, scope, answers, likely_range)
	assumptions = build_design_assumption_records(prompt, scope, answers)
	assumptions.extend(strengthen_design_assumptions(prompt, scope, answers, question_budget))
	unknowns = build_design_unknown_records(prompt, scope, answers, assumptions)
	field_intents = build_design_field_intents(prompt, scope, answers, assumptions, unknowns)
	doctype_strategy = build_design_doctype_strategy(scope, answers)
	scale_model = build_design_scale_model(scope, combined_answers, likely_range)
	structure_model = build_design_structure_model(scope, answers, assumptions)
	content_model = build_design_content_model(scope, answers, assumptions)
	time_model = build_design_time_model(scope, answers, assumptions)
	naming_model = build_design_naming_model(scope, answers, assumptions)
	implementation_requirements = build_design_implementation_requirements(
		prompt,
		scope,
		doctype_strategy,
		scale_model,
		structure_model,
		content_model,
		time_model,
		naming_model,
		field_intents,
	)
	readiness = "needs_question" if scope_type in {"structured_plan", "large_regime", "generic_structured_plan"} or any(unknown.ask for unknown in unknowns) else "ready"
	return DesignInformationMap(
		goal=prompt,
		domain=domain,
		scope_type=scope_type,
		target_doctype="Action",
		question_budget=question_budget,
		doctype_strategy=doctype_strategy,
		scale_model=scale_model,
		structure_model=structure_model,
		content_model=content_model,
		time_model=time_model,
		naming_model=naming_model,
		field_intents=field_intents,
		implementation_requirements=implementation_requirements,
		assumptions=assumptions,
		unknowns=unknowns,
		readiness=readiness,
		readiness_reason="Broad design map needs AI planner review." if scope_type in {"structured_plan", "large_regime", "generic_structured_plan"} else "Map has enough scope, structure, assumptions, and field strategy for implementation.",
	)


def build_design_assumption_records(prompt, scope, answers):
	answer_text = design_answer_text(answers)
	assumptions = [
		DesignAssumption(
			assumption_id="action_doctype_strategy",
			category="doctype",
			statement="Use Action records with parent_action hierarchy for generated structures.",
			reason="The current implementation target is Action and the sync layer resolves parent operation references.",
			confidence=0.86,
			impact="high",
		),
		DesignAssumption(
			assumption_id="leaf_container_split",
			category="structure",
			statement="Container nodes are groups; concrete work items are leaf todo Actions.",
			reason="This makes generated trees inspectable and executable without mixing headings and tasks.",
			confidence=0.82,
			impact="high",
		),
	]
	if not any(term in f"{prompt} {answer_text}".lower() for term in ("calendar", "event", " at ", "am", "pm")):
		assumptions.append(DesignAssumption(
			assumption_id="default_unscheduled_todos",
			category="timing",
			statement="Generate planned todo Actions rather than calendar events unless explicit times are requested.",
			reason="Most large structures should not flood the calendar unless the prompt asks for calendar scheduling.",
			confidence=0.78,
			impact="medium",
		))
	return assumptions


def estimate_design_question_budget(prompt, scope, answers, likely_range):
	answers = answers or []
	text = f"{prompt or ''} {design_answer_text(answers)}".lower()
	min_count, max_count = likely_range or (1, 5)
	complexity_score = 0
	complexity_score += 2 if scope.get("scope_type") == "large_regime" else 0
	complexity_score += 1 if scope.get("scope_type") in {"structured_plan", "generic_structured_plan"} else 0
	complexity_score += 2 if max_count >= 100 else 1 if max_count >= 40 else 0
	complexity_score += sum(1 for term in ("template", "period", "schedule", "hierarchy", "under", "daily", "week", "subjects", "tests", "routine") if term in text)
	low_detail_requested = any(phrase in text for phrase in (
		"not much detail",
		"simple",
		"quick",
		"rough",
		"basic",
		"just decide",
		"you decide",
		"decide for me",
		"make assumptions",
		"use your judgement",
		"use your judgment",
	))
	assumption_review_requested = design_assumption_review_requested(prompt, answers)
	asked_count = len([answer for answer in answers if not answer.get("inferred")])
	return {
		"complexity_score": complexity_score,
		"likely_action_count_range": list(likely_range or []),
		"asked_count": asked_count,
		"question_limit": "ai_planner_decides",
		"low_detail_requested": low_detail_requested,
		"assumption_review_requested": assumption_review_requested,
		"strategy": "ai_planner_decides_until_map_ready",
		"reason": "Complexity is descriptive only. The AI planner decides how many questions are needed to complete the information map.",
	}


def strengthen_design_assumptions(prompt, scope, answers, question_budget):
	text = f"{prompt or ''} {design_answer_text(answers)}".lower()
	assumptions = []

	def add(assumption_id, category, statement, reason, confidence=0.78, impact="medium"):
		assumptions.append(DesignAssumption(
			assumption_id=assumption_id,
			category=category,
			statement=statement,
			reason=reason,
			confidence=confidence,
			impact=impact,
		))

	should_strengthen = question_budget.get("low_detail_requested")
	if not should_strengthen:
		return assumptions
	if not any(term in text for term in ("name", "naming", "called")):
		add(
			"strengthened_naming_rule",
			"naming",
			"Use clear generated names derived from the hierarchy, period/focus/group, and concrete activity.",
			"The user did not specify naming, so the best auditable default is to derive names from structure rather than ask another question.",
			0.82,
			"medium",
		)
	if not any(term in text for term in ("description", "detail", "instruction", "specific")):
		add(
			"strengthened_description_depth",
			"content",
			"Use short practical descriptions that explain what each generated Action is for without overloading the tree.",
			"The user did not request deep field detail, so concise descriptions are more useful than asking another question.",
			0.76,
			"medium",
		)
	if not any(term in text for term in ("calendar", "event", "am", "pm", "specific time", "at ")):
		add(
			"strengthened_timing_rule",
			"timing",
			"Use planned todo Actions by default; schedule only the structure or descriptions unless explicit calendar times are requested.",
			"Large generated systems should avoid flooding the calendar unless the prompt asks for concrete event times.",
			0.78,
			"medium",
		)
	if scope.get("scope_type") in {"structured_plan", "large_regime", "generic_structured_plan"} and not any(term in text for term in ("template", "period", "parent", "child", "under", "hierarchy", "structure", "tree")):
		add(
			"strengthened_structure_rule",
			"structure",
			"Use an inspectable parent group → meaningful subgroups → concrete Action leaves structure.",
			"For broad design requests, this structure is the safest default when the user does not specify tree shape and the question budget is low.",
			0.74,
			"high",
		)
	return assumptions


def apply_question_budget_to_unknowns(unknowns, question_budget):
	remaining = question_budget.get("remaining_questions", 0)
	if remaining <= 0:
		return [unknown.model_copy(update={"ask": False}) for unknown in unknowns]
	askable = [unknown for unknown in unknowns if unknown.ask]
	kept_ids = {unknown.unknown_id for unknown in askable[:remaining]}
	return [
		unknown if unknown.unknown_id in kept_ids else unknown.model_copy(update={"ask": False})
		for unknown in unknowns
	]


def build_design_unknown_records(prompt, scope, answers, assumptions):
	unknowns = []
	answer_text = design_answer_text(answers)
	review_assumptions = design_assumption_review_requested(prompt, answers)
	assumption_text = " ".join(assumption.statement for assumption in assumptions or []).lower()

	def answered_or_implied(*terms):
		text = f"{prompt} {answer_text} {assumption_text}".lower()
		return any(term in text for term in terms)

	def prompt_or_answer_implies(*terms):
		text = f"{prompt} {answer_text}".lower()
		return any(term in text for term in terms)

	def explicit_structure_described():
		return prompt_or_answer_implies("template", "period", "under", "parent", "child", "children", "hierarchy", "structure", "tree", "group", "phase", "copy", "repeat")

	def add(unknown_id, category, question, reason, impact, default_assumption=None, options=None, ask=True):
		if design_answer_for(answers, unknown_id, include_inferred=False):
			return
		unknowns.append(DesignUnknown(
			unknown_id=unknown_id,
			category=category,
			question=question,
			reason=reason,
			impact=impact,
			default_assumption=default_assumption,
			options=options or [],
			ask=ask,
		))

	if scope["scope_type"] in {"structured_plan", "large_regime", "generic_structured_plan"}:
		if not explicit_structure_described():
			add(
				"structure_model",
				"structure",
				"What structure should the generated records have? Include parent/child levels, reusable templates, periods, or grouping rules if they matter.",
				"Structure changes the Action tree and cannot be safely guessed for broad design requests.",
				"high",
				"Use a clear parent → group → concrete Action tree",
				ask=True,
			)
		if not answered_or_implied("name", "naming", "called", "random") and review_assumptions:
			add(
				"naming_rules",
				"naming",
				"What naming rule should generated records follow, or may I use clear generated names from the structure?",
				"Naming affects whether large generated trees are readable and auditable.",
				"medium",
				"Use clear generated names from the structure",
				ask=True,
			)
		if not answered_or_implied("time", "timing", "schedule", "calendar", "am", "pm", "morning", "evening", "when") and review_assumptions:
			add(
				"timing_model",
				"timing",
				"What timing assumptions should be used: unscheduled todos, scheduled parent blocks, or dated child Actions?",
				"Timing affects start/end fields and whether generated records appear as calendar events.",
				"medium",
				"Use unscheduled todos unless specific times are implied",
				ask=True,
			)
		if not answered_or_implied("description", "detail", "instruction", "sets", "steps", "specific") and review_assumptions:
			add(
				"content_detail_model",
				"content",
				"How detailed should each generated Action description be?",
				"Description depth changes field content and operation scale for large designs.",
				"medium",
				"Short practical descriptions",
				ask=True,
			)
	return prioritize_design_unknowns(unknowns)


def identify_design_questions_from_map(information_map):
	information_map = DesignInformationMap.model_validate(information_map)
	question = next((unknown for unknown in information_map.unknowns if unknown.ask), None)
	if not question:
		return []
	return [DesignQuestion(
		question_id=question.unknown_id,
		phase=design_question_phase_for_category(question.category),
		question=question.question,
		reason=question.reason,
		options=question.options,
		default_assumption=question.default_assumption,
		required=True,
	)]


def prioritize_design_unknowns(unknowns):
	impact_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}
	return sorted(unknowns, key=lambda unknown: (not unknown.ask, -impact_score.get(unknown.impact, 0), unknown.unknown_id))


def design_question_phase_for_category(category):
	return {
		"scope": "scope",
		"structure": "structure",
		"content": "specifics",
		"naming": "specifics",
		"timing": "extent",
		"fields": "specifics",
		"doctype": "assumptions",
	}.get(category, "assumptions")


def build_design_doctype_strategy(scope, answers):
	return {
		"doctype": "Action",
		"hierarchy_field": "parent_action",
		"group_field": "is_group",
		"concrete_work_field": "todo",
		"calendar_field": "event",
	}


def build_design_scale_model(scope, answers, likely_range):
	requested_count = extract_requested_action_count(design_answer_text(answers))
	return {
		"likely_action_count_range": list(likely_range),
		"requested_count": requested_count or None,
		"reason": "Scale is estimated from prompt scope, explicit counts, and answered detail level.",
	}


def build_design_structure_model(scope, answers, assumptions):
	answer_text = design_answer_text(answers)
	structure_answers = answers_for_design_category(answers, "structure")
	structure_answer = "\n".join(structure_answers) or None
	structural_terms = extract_structural_terms(answer_text)
	if "subject-first" in answer_text:
		structure = "subject-first"
	elif "time-first" in answer_text:
		structure = "time-first"
	elif "template" in answer_text and any(term in answer_text for term in ("period", "instance", "copy", "repeat", "schedule")):
		structure = "reusable template layer → generated period/instance groups → concrete Actions"
	elif structural_terms:
		structure = " → ".join(structural_terms[:4]) + " → concrete Actions"
	else:
		structure = "hybrid parent → domain groups → time/detail groups → concrete Actions"
	return {
		"structure": structure,
		"parent_groups": True,
		"children_are_todos": True,
		"structure_answer": structure_answer,
		"structural_terms": structural_terms,
		"relationship_terms": extract_relationship_terms(answer_text),
		"template_layer_requested": "template" in answer_text or "reusable" in answer_text,
		"period_or_instance_layer_requested": any(term in answer_text for term in ("period", "week", "month", "day", "daily", "copy", "repeat", "schedule", "instance")),
	}


def build_design_content_model(scope, answers, assumptions):
	detail_answers = answers_for_design_category(answers, "content") + answers_for_design_category(answers, "fields")
	naming_detail = design_answer_for(answers, "workout_naming_and_detail") or design_answer_for(answers, "workout_execution_detail") or "\n".join(detail_answers) or None
	return {
		"domain": scope["domain"],
		"source": "generated_or_inferred",
		"answers": answers,
		"content_assumptions": [assumption.statement for assumption in assumptions if assumption.category == "content"],
		"naming_and_detail_answer": naming_detail,
		"ordered_content_requested": bool(naming_detail) and any(term in naming_detail.lower() for term in ("right order", "order", "sequence", "precedence", "first", "then", "copy and paste")),
		"detail_terms": extract_content_detail_terms(naming_detail or design_answer_text(answers)),
	}


def build_design_time_model(scope, answers, assumptions):
	answer_text = design_answer_text(answers)
	timing_requested = any(term in answer_text for term in ("right time", "when each", "schedule", "calendar", "period", "week", "daily", "every", "morning", "evening")) or bool(re.search(r"\b(?:am|pm)\b", answer_text))
	return {
		"scheduling_style": "todos_not_calendar_events",
		"default_status": "Upcoming",
		"timing_assumptions": [assumption.statement for assumption in assumptions if assumption.category == "timing"],
		"period_answer": "\n".join(answers_for_design_category(answers, "timing") + answers_for_design_category(answers, "structure")) or None,
		"schedule_pattern": infer_schedule_pattern_from_text(answer_text),
		"practical_timing_required": timing_requested,
		"timing_terms": extract_timing_terms(answer_text),
	}


def build_design_naming_model(scope, answers, assumptions):
	answer = design_answer_for(answers, "workout_naming_and_detail") or design_answer_for(answers, "naming_rules")
	return {
		"strategy": answer or "clear_generated_names",
		"assumptions": [assumption.statement for assumption in assumptions if assumption.category == "naming"],
	}


def build_design_implementation_requirements(prompt, scope, doctype_strategy, scale_model, structure_model, content_model, time_model, naming_model, field_intents):
	requirements = []
	add_design_requirement(requirements, "target_doctype", "doctype", f"Implementation must create or interact with {doctype_strategy.get('doctype', 'Action')} records using the mapped DocType strategy.", [doctype_strategy.get("doctype"), doctype_strategy.get("hierarchy_field"), doctype_strategy.get("group_field")], "Use the target DocType fields and relationship fields from the information map.")
	if scale_model.get("requested_count"):
		add_design_requirement(requirements, "requested_count", "scope", f"Implementation must preserve the requested scale of about {scale_model.get('requested_count')} concrete Actions unless security or validation blocks it.", [str(scale_model.get("requested_count")), "count", "scale"], "Set target counts/templates so deterministic expansion can reach the requested scale.")
	if scope.get("scope_type") != "simple_action" and structure_model.get("structure"):
		add_design_requirement(requirements, "structure_shape", "structure", f"Implementation must preserve this structure: {structure_model.get('structure')}.", [structure_model.get("structure"), *(structure_model.get("structural_terms") or [])], "Represent the structure with parent groups, child groups, template variables, or relationship fields.")
	if structure_model.get("template_layer_requested"):
		add_design_requirement(requirements, "template_layer", "template", "Implementation must preserve the requested reusable/template layer instead of flattening directly to leaf records.", ["template", "reusable", "copy", "repeat"], "Use blueprint groups/templates/notes to distinguish reusable pattern from generated instances.")
	if structure_model.get("period_or_instance_layer_requested"):
		add_design_requirement(requirements, "period_instance_layer", "relationship", "Implementation must preserve the requested period/instance layer for generated records.", ["period", "instance", "day", "week", "schedule", "repeat"], "Use groups or template variables for periods, days, sessions, or repeated instances when the map contains them.")
	if structure_model.get("relationship_terms"):
		add_design_requirement(requirements, "relationship_terms", "relationship", "Implementation must preserve explicit relationship and ordering terms from the user answers.", structure_model.get("relationship_terms"), "Map relationship terms into parent links, group hierarchy, ordering, descriptions, or template variables.")
	if time_model.get("practical_timing_required"):
		add_design_requirement(requirements, "practical_timing", "timing", "Implementation must preserve practical timing and scheduling assumptions instead of relying only on compiler defaults.", time_model.get("timing_terms") or ["time", "schedule", "when"], "Represent timing in names, descriptions, template variables, or Action start/end fields as appropriate.")
	if content_model.get("ordered_content_requested"):
		add_design_requirement(requirements, "ordered_content", "content", "Implementation must preserve requested sequence/order/precedence in generated record names or descriptions.", ["order", "sequence", "first", "then", *(content_model.get("detail_terms") or [])], "Encode order in generated names, descriptions, or template variables.")
	if naming_model.get("strategy") and naming_model.get("strategy") != "clear_generated_names":
		add_design_requirement(requirements, "naming_strategy", "naming", f"Implementation must preserve the naming strategy: {naming_model.get('strategy')}.", [naming_model.get("strategy"), "name", "naming"], "Reflect naming strategy in name patterns and generated record titles.")
	for intent in field_intents:
		if intent.value_strategy in {"user_provided", "inferred", "assumed"} and intent.value not in (None, ""):
			add_design_requirement(requirements, f"field_{intent.fieldname}", "fields", f"Implementation should preserve {intent.label or intent.fieldname} field intent as {intent.value!r} where relevant.", [intent.fieldname, intent.label, str(intent.value)], "Set or explain this field in blueprint templates, groups, or compiled operations.", must_preserve=False)
	return requirements


def add_design_requirement(requirements, requirement_id, category, description, evidence, blueprint_hint, must_preserve=True):
	requirements.append(DesignImplementationRequirement(
		requirement_id=requirement_id,
		category=category,
		description=description,
		evidence=[str(item) for item in evidence or [] if item],
		must_preserve=must_preserve,
		blueprint_hint=blueprint_hint,
		validation_terms=list(dict.fromkeys(term for item in evidence or [] for term in extract_contract_terms(item))),
	))


def answers_for_design_category(answers, category):
	return [str(answer.get("answer") or "") for answer in answers or [] if design_question_category_for_id(answer.get("question_id")) == category and answer.get("answer")]


def design_question_category_for_id(question_id):
	question_id = str(question_id or "").lower()
	if any(term in question_id for term in ("structure", "hierarchy", "tree", "scope")):
		return "structure"
	if any(term in question_id for term in ("time", "timing", "schedule", "horizon", "period")):
		return "timing"
	if any(term in question_id for term in ("name", "naming", "detail", "description")):
		return "naming"
	if any(term in question_id for term in ("field", "doctype")):
		return "fields"
	return "content"


def extract_structural_terms(text):
	terms = []
	for term in ("template", "period", "week", "day", "session", "phase", "subject", "topic", "module", "milestone", "focus", "category", "group", "test", "revision"):
		if term in (text or ""):
			terms.append(term)
	return list(dict.fromkeys(terms))


def extract_relationship_terms(text):
	terms = []
	for term in ("under", "parent", "child", "children", "before", "after", "precedence", "first", "second", "then", "copy", "paste", "repeat", "cycle", "cycling", "every", "per"):
		if term in (text or ""):
			terms.append(term)
	return list(dict.fromkeys(terms))


def extract_content_detail_terms(text):
	terms = []
	for term in ("description", "detail", "instruction", "order", "sequence", "specific", "practical", "step", "test", "revision", "exercise", "subject"):
		if term in (text or ""):
			terms.append(term)
	return list(dict.fromkeys(terms))


def extract_timing_terms(text):
	terms = []
	for term in ("time", "timing", "schedule", "calendar", "period", "week", "day", "daily", "morning", "afternoon", "evening", "night", "am", "pm", "every", "right time"):
		if term in (text or ""):
			terms.append(term)
	return list(dict.fromkeys(terms))



def build_system_assumptions_for_design(scope, answers=None):
	return [
		"Use Action records for the generated structure.",
		"Use parent_action links for hierarchy.",
		"Use is_group=1 for container Actions and todo=1 for concrete work Actions.",
		"Use event=0 unless the user explicitly asks for calendar scheduling.",
		"Use status='Upcoming' for new planned Actions.",
	]


def next_design_question(plan):
	plan = DesignQuestionPlan.model_validate(plan)
	return plan.questions[0] if plan.questions else None


def design_interview_is_complete(plan):
	plan = DesignQuestionPlan.model_validate(plan)
	return not plan.questions


def compile_design_brief(prompt, plan, answers):
	plan = DesignQuestionPlan.model_validate(plan)
	answers = answers or []
	information_map = plan.information_map or build_design_information_map(
		prompt,
		{
			"scope_type": plan.scope_type,
			"domain": plan.domain,
			"likely_action_count_range": plan.likely_action_count_range,
			"answers": answers,
		},
		answers,
	)
	answer_lines = [f"{answer.get('question_id')}: {answer.get('answer')}" for answer in answers]
	map_json = information_map.model_dump_json(indent=2)
	return {
		"design_type": plan.scope_type,
		"domain": plan.domain,
		"likely_action_count_range": list(plan.likely_action_count_range),
		"answers": answers,
		"system_assumptions": plan.system_assumptions,
		"information_map": information_map.model_dump(mode="json"),
		"clarified_prompt": (
			f"{prompt}\n\nDesign information map:\n{map_json}\n\nProgressive design interview answers:\n"
			+ "\n".join(answer_lines)
			+ "\n\nSystem assumptions:\n"
			+ "\n".join(f"- {assumption}" for assumption in plan.system_assumptions)
		),
	}


def run_preview_clarification_stage(state):
	prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nCurrent datetime:\n{_now().isoformat()}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		"\n\nPreview pipeline: clarify once. If the prompt includes a Design information map, "
		"treat that map and the progressive interview answers as clarification context."
	)
	result = _run_agent_sync_with_retry(
		get_clarification_agent(),
		prompt=prompt,
		deps=state,
		conversation_id=state.orchestration_id,
	)
	if isinstance(result.output, UserClarification):
		state.user_clarification = result.output
		state.stage = "waiting_for_user"
		return result.output
	state.clarification = result.output
	state.stage = "route_selection"
	return run_preview_assumption_review(state, result.output)


def run_preview_assumption_review(state, clarification):
	review_prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nCurrent datetime:\n{_now().isoformat()}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		f"\n\nClarification questions proposed:\n{clarification.model_dump_json()}"
	)
	review = _run_agent_sync_with_retry(
		get_assumption_review_agent(),
		prompt=review_prompt,
		deps=state,
		conversation_id=state.orchestration_id,
	)
	state.assumption_review = review.output
	state.assumption_notifications.extend(build_assumption_notifications(review.output))
	if review.output.remaining_questions:
		state.user_clarification = assumption_review_to_user_clarification(review.output)
		state.stage = "waiting_for_user"
		return state.user_clarification
	state.clarification = assumption_review_to_clarification(review.output)
	state.user_clarification = None
	state.stage = "route_selection"
	return state.clarification


def run_preview_route_selection_stage(state):
	prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nClarification:\n{state.clarification.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		"\n\nPreview pipeline: select the route once and return the stage result."
	)
	result = _run_agent_sync_with_retry(
		get_route_selection_agent(),
		prompt=prompt,
		deps=state,
		conversation_id=state.orchestration_id,
	)
	state.route_selection = result.output
	chosen_route = next(route for route in result.output.routes if route.route_id == result.output.chosen_route_id)
	if chosen_route.outcome_type == "ask_user":
		state.user_clarification = route_selection_to_user_clarification(result.output)
		state.stage = "waiting_for_user"
		return state.user_clarification
	state.stage = "implementation"
	return result.output


def run_preview_implementation_stage(state):
	chosen_route = next(route for route in state.route_selection.routes if route.route_id == state.route_selection.chosen_route_id)
	if should_use_action_blueprint_station(state):
		blueprint_result = _run_agent_sync_with_retry(
			get_action_blueprint_agent(),
			prompt=build_action_blueprint_prompt(state, chosen_route),
			deps=state,
			conversation_id=state.orchestration_id,
		)
		if isinstance(blueprint_result.output, UserClarification):
			state.user_clarification = blueprint_result.output
			state.stage = "waiting_for_user"
			return blueprint_result.output
		state.action_design = action_implementation_design_from_blueprint(state.input.input, blueprint_result.output)
		state.execution_plan = compile_execution_plan(state)
		state.stage = "execution"
		return state.execution_plan
	prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nClarification:\n{state.clarification.model_dump_json()}"
		f"\n\nChosen route:\n{chosen_route.model_dump_json()}"
		f"\n\nRoute selection:\n{state.route_selection.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nCurrent datetime:\n{_now().isoformat()}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		f"\n\nExecution bus contract:\nReturn operations, not actions. "
		f"Each operation needs operation_type, operation_family, operation_id, decision_id, description, and operation-specific input. "
		f"Use doctype.create/update/delete for DocType records. Other families are report, dashboard, scheduler, notification, and external. "
		f"Cover every explicit user intent. Do not drop create/update/delete/check sub-requests from compound prompts."
		"\n\nPreview pipeline: design implementation once and return the execution plan."
	)
	result = _run_agent_sync_with_retry(
		get_action_design_agent(),
		prompt=prompt,
		deps=state,
		conversation_id=state.orchestration_id,
	)
	if isinstance(result.output, UserClarification):
		state.user_clarification = result.output
		state.stage = "waiting_for_user"
		return result.output
	state.action_design = result.output
	normalize_action_design(state.action_design, chosen_route, state)
	state.execution_plan = compile_execution_plan(state)
	state.stage = "execution"
	return state.execution_plan


def preview_execution_security_for_plan(plan):
	remember_execution_plan(plan)
	return summarize_execution_preparation(remember_execution_preparation(prepare_execution(plan)))


def preview_execution_approval_for_plan(plan, decisions):
	remember_execution_plan(plan)
	preparation = remember_execution_preparation(prepare_execution(plan))
	return summarize_execution_approval_result(apply_execution_approvals(preparation, decisions))


def preview_approve_cached_execution(plan_id, group_id=None, confirmation_phrase=None):
	preparation = get_cached_execution_preparation(plan_id)
	prompts = preparation.security_review.approval_prompts
	selected_prompts = [prompt for prompt in prompts if group_id in {None, prompt.group_id}]
	if group_id and not selected_prompts:
		raise ValueError(f"Approval group {group_id} was not found for plan {plan_id}")
	decisions = [
		ExecutionApprovalDecision(
			group_id=prompt.group_id,
			approved=True,
			confirmation_phrase=confirmation_phrase,
		)
		for prompt in selected_prompts
	]
	return summarize_execution_approval_result(apply_execution_approvals(preparation, decisions))


def approve_and_sync_cached_execution(plan_id, group_id=None, confirmation_phrase=None):
	plan = get_cached_execution_plan(plan_id)
	preparation = get_cached_execution_preparation(plan_id)
	prompts = preparation.security_review.approval_prompts
	selected_prompts = [prompt for prompt in prompts if group_id in {None, prompt.group_id}]
	if group_id and not selected_prompts:
		raise ValueError(f"Approval group {group_id} was not found for plan {plan_id}")
	decisions = [
		ExecutionApprovalDecision(
			group_id=prompt.group_id,
			approved=True,
			confirmation_phrase=confirmation_phrase,
		)
		for prompt in selected_prompts
	]
	approval_result = apply_execution_approvals(preparation, decisions)
	report = sync_approved_execution(plan, approval_result)
	return {
		"approval_result": summarize_execution_approval_result(approval_result),
		"sync_report": summarize_execution_sync_report(report),
	}


def preview_reject_cached_execution(plan_id, group_id=None, note=None):
	preparation = get_cached_execution_preparation(plan_id)
	prompts = preparation.security_review.approval_prompts
	selected_prompts = [prompt for prompt in prompts if group_id in {None, prompt.group_id}]
	if group_id and not selected_prompts:
		raise ValueError(f"Approval group {group_id} was not found for plan {plan_id}")
	decisions = [
		ExecutionApprovalDecision(group_id=prompt.group_id, approved=False, note=note)
		for prompt in selected_prompts
	]
	return summarize_execution_approval_result(apply_execution_approvals(preparation, decisions))


def preview_sample_create_security(count=10):
	return summarize_execution_preparation(build_sample_create_preparation(count))


def preview_sample_delete_security(count=10):
	plan = build_sample_delete_plan(count)
	evaluations = [
		OperationSecurityEvaluation(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			security_group_key=security_group_key_for_operation(operation, 0.8),
			permission_type="delete",
			permission_allowed=True,
			risk_level="high",
			risk_score=0.8,
			approval_required=True,
			explicit_confirmation_required=True,
			reasons=["Synthetic preview: deletes are destructive and require approval."],
		)
		for operation in plan.operations
	]
	prompts = group_execution_approvals(evaluations)
	queue = build_execution_queue(plan.operations, evaluations, prompts)
	review = ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status="waiting_for_approval",
		overall_risk_level="high",
		overall_risk_score=max(prompt.risk_score for prompt in prompts) if prompts else 0.8,
		operation_evaluations=evaluations,
		approval_prompts=prompts,
		queue=queue,
	)
	return summarize_execution_preparation(ExecutionPreparation(
		plan_id=plan.plan_id,
		status=review.status,
		security_review=review,
	))


def preview_sample_create_approval(count=10, approve=True):
	preparation = build_sample_create_preparation(count)
	decisions = [
		ExecutionApprovalDecision(group_id=prompt.group_id, approved=approve)
		for prompt in preparation.security_review.approval_prompts
	]
	return summarize_execution_approval_result(apply_execution_approvals(preparation, decisions))


def preview_sample_delete_approval(count=10, confirmation_phrase=None, approve=True):
	preparation_summary = preview_sample_delete_security(count)
	preparation = ExecutionPreparation(
		plan_id=preparation_summary["plan_id"],
		status=preparation_summary["status"],
		security_review=ExecutionSecurityReview(
			plan_id=preparation_summary["plan_id"],
			status=preparation_summary["status"],
			overall_risk_level=preparation_summary["overall_risk_level"],
			overall_risk_score=preparation_summary["overall_risk_score"],
			blocked_reasons=preparation_summary["blocked_reasons"],
			approval_prompts=preparation_summary["approval_prompts"],
			operation_evaluations=preparation_summary["operation_evaluations"],
			queue=preparation_summary["queue"],
		),
	)
	decisions = [
		ExecutionApprovalDecision(
			group_id=prompt.group_id,
			approved=approve,
			confirmation_phrase=confirmation_phrase,
		)
		for prompt in preparation.security_review.approval_prompts
	]
	return summarize_execution_approval_result(apply_execution_approvals(preparation, decisions))


def preview_sample_partial_approval():
	preparation = build_mixed_approval_sample_preparation()
	first_prompt = preparation.security_review.approval_prompts[0]
	decision = ExecutionApprovalDecision(
		group_id=first_prompt.group_id,
		approved=True,
		confirmation_phrase=first_prompt.confirmation_phrase,
	)
	return {
		"security_preparation": summarize_execution_preparation(preparation),
		"approval_result": summarize_execution_approval_result(apply_execution_approvals(preparation, [decision])),
	}


def preview_sample_create_then_delete_sync():
	plan = build_create_then_delete_sample_plan()
	preparation = build_execution_security_review_from_evaluations(
		plan,
		[evaluate_operation_security(plan, operation) for operation in plan.operations],
	)
	preparation = ExecutionPreparation(plan_id=plan.plan_id, status=preparation.status, security_review=preparation)
	decisions = [
		ExecutionApprovalDecision(
			group_id=prompt.group_id,
			approved=True,
			confirmation_phrase=prompt.confirmation_phrase,
		)
		for prompt in preparation.security_review.approval_prompts
	]
	approval_result = apply_execution_approvals(preparation, decisions)
	report = sync_approved_execution(plan, approval_result)
	return {
		"security_preparation": summarize_execution_preparation(preparation),
		"approval_result": summarize_execution_approval_result(approval_result),
		"sync_report": summarize_execution_sync_report(report),
	}


def preview_sample_tree_create_sync():
	plan = build_sample_tree_create_plan()
	preparation = prepare_execution(plan)
	decisions = [
		ExecutionApprovalDecision(
			group_id=prompt.group_id,
			approved=True,
			confirmation_phrase=prompt.confirmation_phrase,
		)
		for prompt in preparation.security_review.approval_prompts
	]
	approval_result = apply_execution_approvals(preparation, decisions)
	report = sync_approved_execution(plan, approval_result)
	return {
		"plan": plan.model_dump(),
		"security_preparation": summarize_execution_preparation(preparation),
		"approval_result": summarize_execution_approval_result(approval_result),
		"sync_report": summarize_execution_sync_report(report),
	}


def build_sample_tree_create_plan():
	now = _now().replace(second=0, microsecond=0)
	parent = CreateRecord(
		operation_id="sample_tree_parent",
		decision_id="sample_tree_decision",
		description="Create parent Action for tree dependency test.",
		doctype="Action",
		fields={
			"action_name": f"Tree Parent Test {now.strftime('%H%M')}",
			"description": "Parent Action created to validate same-plan tree linking.",
			"start_date": now.isoformat(),
			"end_date": (now + timedelta(hours=1)).isoformat(),
			"is_group": True,
			"status": "Upcoming",
		},
	)
	child = CreateRecord(
		operation_id="sample_tree_child",
		decision_id="sample_tree_decision",
		description="Create child Action under parent using parent operation id.",
		doctype="Action",
		fields={
			"action_name": f"Tree Child Test {now.strftime('%H%M')}",
			"description": "Child Action linked to parent created earlier in the same execution plan.",
			"start_date": (now + timedelta(minutes=10)).isoformat(),
			"end_date": (now + timedelta(minutes=40)).isoformat(),
			"parent_action": "sample_tree_parent",
			"todo": True,
			"status": "Upcoming",
		},
	)
	return ExecutionPlan(
		plan_id=str(uuid4()),
		problem=ProblemBreakdown(goal="Validate same-plan Action tree creation."),
		routes_considered=[RouteOption(
			route_id="sample_tree_create",
			outcome_type="create",
			description="Create parent and child Action records in one plan.",
			expected_outcome="Child Action links to the parent Action created earlier in the plan.",
			system_objects=["Action"],
			evidence=[Evidence(source="system", reference="sample", fact="Tree creation sync validation.")],
			confidence=1,
			score=1,
		)],
		chosen_route_id="sample_tree_create",
		decisions=[Decision(
			decision_id="sample_tree_decision",
			question="Can child records reference parent operations?",
			conclusion="The execution bus should resolve parent operation ids to created record names.",
			evidence=[Evidence(source="system", reference="Action.parent_action", fact="Action uses parent_action for hierarchy.")],
			confidence=1,
		)],
		operations=normalize_plan_operation_dependencies([parent, child]),
		success_criteria=[SuccessCriterion(
			description="Parent and child created.",
			check="Child parent_action equals created parent Action name.",
			expected_result="Both records sync successfully and child links to parent.",
		)],
	)


def preview_clear_calendar_security(period="this_week", limit=50):
	start, end = resolve_period_bounds(period)
	records = query_calendar_records_for_execution(start, end, limit)
	if not records:
		return {
			"period": period,
			"start": start.isoformat(),
			"end": end.isoformat(),
			"record_count": 0,
			"message": "No calendar Action records found for this period.",
			"security_preparation": None,
		}
	plan = build_calendar_delete_execution_plan(period, start, end, records)
	return {
		"period": period,
		"start": start.isoformat(),
		"end": end.isoformat(),
		"record_count": len(records),
		"records": _json_safe(records),
		"security_preparation": summarize_execution_preparation(prepare_execution(plan)),
	}


def resolve_period_bounds(period):
	period = period.lower().strip()
	now = _now()
	if period in {"today", "day"}:
		return _day_bounds(now)
	if period in {"this_week", "week"}:
		return _week_bounds(now)
	if period in {"next_week"}:
		next_week = now + timedelta(days=7)
		return _week_bounds(next_week)
	if period in {"this_month", "month"}:
		return _month_bounds(now)
	if period in {"next_month"}:
		next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
		return _month_bounds(next_month)
	raise ValueError("Supported periods: today, this_week, next_week, this_month, next_month")


def query_calendar_records_for_execution(start, end, limit=50):
	import frappe

	limit = max(1, min(int(limit), 100))
	records = frappe.get_list(
		"Action",
		filters=[
			["Action", "event", "=", 1],
			["Action", "start_date", "<=", end],
			["Action", "end_date", ">=", start],
		],
		fields=[
			"name",
			"action_name",
			"start_date",
			"end_date",
			"event",
			"is_group",
			"goal",
			"basegoal",
			"parent_action",
			"modified",
		],
		order_by="start_date asc",
		limit_page_length=limit,
	)
	return _json_safe(records)


def build_calendar_delete_execution_plan(period, start, end, records):
	operations = [
		DeleteRecord(
			operation_id=f"delete_calendar_event_{index + 1}",
			decision_id="delete_calendar_events_decision",
			description=f"Delete calendar Action {record.get('action_name') or record.get('name')} from {period}.",
			doctype="Action",
			record_id=record["name"],
			expected_modified=_coerce_datetime(record["modified"]),
		)
		for index, record in enumerate(records)
	]
	return ExecutionPlan(
		plan_id=f"clear_calendar_{period}",
		problem=ProblemBreakdown(goal=f"Clear calendar records for {period}."),
		routes_considered=[RouteOption(
			route_id="clear_calendar_direct_security_preview",
			outcome_type="delete",
			description=f"Delete {len(records)} calendar Action records between {start.isoformat()} and {end.isoformat()}.",
			expected_outcome="Execution security preparation determines required grouped approvals before any delete.",
			system_objects=["Action"],
			evidence=[Evidence(source="system", reference="query_calendar_records_for_execution", fact=f"Found {len(records)} calendar Action records in the selected period.")],
			missing_information=[],
			reversibility="low",
			risks=["Deletes are destructive and require execution-bus approval."],
			confidence=1,
			score=1,
		)],
		chosen_route_id="clear_calendar_direct_security_preview",
		decisions=[Decision(
			decision_id="delete_calendar_events_decision",
			question="Which existing calendar events would be deleted?",
			conclusion=f"Delete the {len(records)} queried calendar Action records after grouped approval.",
			evidence=[Evidence(source="system", reference="query_calendar_records_for_execution", fact="Records include exact names and modified timestamps for stale checks.")],
			confidence=1,
		)],
		operations=operations,
		success_criteria=[SuccessCriterion(
			description="Verify calendar records were removed after execution.",
			check="Query Action records in the same period with event enabled.",
			expected_result="The deleted records are no longer present after approved execution.",
		)],
	)


def build_sample_create_plan(count=10):
	count = max(1, min(int(count), 50))
	start = _now().replace(hour=9, minute=0, second=0, microsecond=0)
	operations = []
	for index in range(count):
		operation_start = start + timedelta(days=index)
		operation_end = operation_start + timedelta(hours=1)
		operations.append(CreateRecord(
			operation_id=f"sample_create_action_{index + 1}",
			decision_id="sample_create_decision",
			description=f"Create sample calendar Action {index + 1} for security grouping preview.",
			doctype="Action",
			fields={
				"action_name": f"Sample security event {index + 1}",
				"description": "Sample event for execution-bus security grouping preview.",
				"start_date": operation_start.isoformat(),
				"end_date": operation_end.isoformat(),
				"event": True,
				"todo": False,
				"status": "Upcoming",
			},
		))
	return build_sample_execution_plan("sample_create_plan", "Preview grouped create approval", operations)


def build_sample_create_preparation(count=10):
	plan = build_sample_create_plan(count)
	evaluations = [
		OperationSecurityEvaluation(
			operation_id=operation.operation_id,
			operation_type=operation.operation_type,
			operation_family=operation.operation_family,
			security_group_key=security_group_key_for_operation(operation, 0.25),
			permission_type="create",
			permission_allowed=True,
			risk_level="low",
			risk_score=0.25,
			approval_required=True,
			explicit_confirmation_required=False,
			reasons=["Synthetic preview: creates are grouped for one approval."],
		)
		for operation in plan.operations
	]
	prompts = group_execution_approvals(evaluations)
	queue = build_execution_queue(plan.operations, evaluations, prompts)
	review = ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status="waiting_for_approval",
		overall_risk_level="low",
		overall_risk_score=max(prompt.risk_score for prompt in prompts) if prompts else 0.25,
		operation_evaluations=evaluations,
		approval_prompts=prompts,
		queue=queue,
	)
	return ExecutionPreparation(
		plan_id=plan.plan_id,
		status=review.status,
		security_review=review,
	)


def build_sample_delete_plan(count=10):
	count = max(1, min(int(count), 50))
	modified = _now()
	operations = [
		DeleteRecord(
			operation_id=f"sample_delete_action_{index + 1}",
			decision_id="sample_delete_decision",
			description=f"Delete sample Action {index + 1} for security grouping preview.",
			doctype="Action",
			record_id=f"SAMPLE-ACTION-{index + 1}",
			expected_modified=modified,
		)
		for index in range(count)
	]
	return build_sample_execution_plan("sample_delete_plan", "Preview grouped delete approval", operations)


def build_mixed_approval_sample_plan():
	now = _now()
	operations = [
		CreateRecord(
			operation_id="mixed_create_action_1",
			decision_id="mixed_approval_decision",
			description="Create one sample Action for mixed approval preview.",
			doctype="Action",
			fields={
				"action_name": "Mixed approval sample event",
				"description": "Sample event for partial approval preview.",
				"start_date": now.replace(hour=9, minute=0, second=0, microsecond=0).isoformat(),
				"end_date": now.replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
				"event": True,
				"todo": False,
				"status": "Upcoming",
			},
		),
		DeleteRecord(
			operation_id="mixed_delete_action_1",
			decision_id="mixed_approval_decision",
			description="Delete one sample Action for mixed approval preview.",
			doctype="Action",
			record_id="SAMPLE-MIXED-DELETE-1",
			expected_modified=now,
		),
	]
	return build_sample_execution_plan("mixed_approval_sample_plan", "Preview partial approval handling", operations)


def build_mixed_approval_sample_preparation():
	plan = build_mixed_approval_sample_plan()
	evaluations = [
		OperationSecurityEvaluation(
			operation_id="mixed_create_action_1",
			operation_type="doctype.create",
			operation_family="doctype",
			security_group_key="doctype.create:Action",
			permission_type="create",
			permission_allowed=True,
			risk_level="low",
			risk_score=0.25,
			approval_required=True,
			reasons=["Synthetic preview: create operation requires grouped approval."],
		),
		OperationSecurityEvaluation(
			operation_id="mixed_delete_action_1",
			operation_type="doctype.delete",
			operation_family="doctype",
			security_group_key="doctype.delete:Action",
			permission_type="delete",
			permission_allowed=True,
			risk_level="high",
			risk_score=0.8,
			approval_required=True,
			explicit_confirmation_required=True,
			reasons=["Synthetic preview: delete operation requires explicit confirmation."],
		),
	]
	prompts = group_execution_approvals(evaluations)
	queue = build_execution_queue(plan.operations, evaluations, prompts)
	review = ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status="waiting_for_approval",
		overall_risk_level="high",
		overall_risk_score=max(prompt.risk_score for prompt in prompts),
		operation_evaluations=evaluations,
		approval_prompts=prompts,
		queue=queue,
	)
	return ExecutionPreparation(
		plan_id=plan.plan_id,
		status=review.status,
		security_review=review,
	)


def build_create_then_delete_sample_plan():
	now = _now().replace(hour=21, minute=30, second=0, microsecond=0)
	create_operation = CreateRecord(
		operation_id="sample_create_temporary_event",
		decision_id="sample_create_then_delete_decision",
		description="Create a temporary event for dependency delete validation.",
		doctype="Action",
		fields={
			"action_name": "Temporary dependency delete test",
			"description": "Temporary event used to validate create-then-delete sync.",
			"start_date": now.isoformat(),
			"end_date": (now + timedelta(minutes=30)).isoformat(),
			"event": True,
			"todo": False,
			"status": "Upcoming",
		},
	)
	delete_operation = DeleteRecord(
		operation_id="sample_delete_temporary_event",
		decision_id="sample_create_then_delete_decision",
		description="Delete the temporary event created by the previous operation.",
		doctype="Action",
		dependencies=[OperationDependency(target="operation", operation_id=create_operation.operation_id)],
	)
	return build_sample_execution_plan(
		"sample_create_then_delete_plan",
		"Preview create-then-delete dependency sync",
		[create_operation, delete_operation],
	)


def preview_security_normalization_regression():
	plan = build_create_then_delete_sample_plan()
	deterministic_evaluations = [evaluate_operation_security(plan, operation) for operation in plan.operations]
	prompts = group_execution_approvals(deterministic_evaluations)
	weakened_prompts = [prompt.model_copy(deep=True) for prompt in prompts]
	weakened_evaluations = [evaluation.model_copy(deep=True) for evaluation in deterministic_evaluations]
	for prompt in weakened_prompts:
		if prompt.group_key == "doctype.delete:Action":
			prompt.explicit_confirmation_required = False
			prompt.confirmation_phrase = None
	for evaluation in weakened_evaluations:
		if evaluation.operation_type == "doctype.delete":
			evaluation.explicit_confirmation_required = False
	weakened_review = ExecutionSecurityReview(
		plan_id=plan.plan_id,
		status="waiting_for_approval",
		overall_risk_level="high",
		overall_risk_score=0.8,
		operation_evaluations=weakened_evaluations,
		approval_prompts=weakened_prompts,
		queue=build_execution_queue(plan.operations, weakened_evaluations, weakened_prompts),
	)
	normalized = normalize_execution_security_review(plan, weakened_review, deterministic_evaluations)
	return summarize_execution_preparation(ExecutionPreparation(
		plan_id=plan.plan_id,
		status=normalized.status,
		security_review=normalized,
	))


def build_sample_execution_plan(plan_id, goal, operations):
	decision_id = operations[0].decision_id
	return ExecutionPlan(
		plan_id=plan_id,
		problem=ProblemBreakdown(goal=goal),
		routes_considered=[RouteOption(
			route_id="sample_security_route",
			outcome_type="delete" if any(isinstance(operation, DeleteRecord) for operation in operations) else "create",
			description="Synthetic route used only to preview execution-bus security grouping.",
			expected_outcome="Security preparation is returned without executing anything.",
			system_objects=["Action"],
			evidence=[Evidence(source="system", reference="preview helper", fact="This plan is synthetic and does not mutate records.")],
			reversibility="medium",
			risks=["Synthetic preview only."],
			confidence=1,
			score=1,
		)],
		chosen_route_id="sample_security_route",
		decisions=[Decision(
			decision_id=decision_id,
			question="How should security grouping be previewed?",
			conclusion="Use synthetic operations so approval grouping can be tested without Gemini or database mutations.",
			evidence=[Evidence(source="system", reference="preview helper", fact="Synthetic operations are passed through the execution-bus security layer only.")],
			confidence=1,
		)],
		operations=operations,
		success_criteria=[SuccessCriterion(
			description="Security preparation is produced.",
			check="Inspect the approval groups and queue.",
			expected_result="No records are mutated.",
		)],
	)


def summarize_execution_preparation(preparation):
	preparation = ExecutionPreparation.model_validate(preparation)
	review = preparation.security_review
	return {
		"plan_id": preparation.plan_id,
		"status": preparation.status,
		"overall_risk_level": review.overall_risk_level,
		"overall_risk_score": review.overall_risk_score,
		"blocked_reasons": review.blocked_reasons,
		"approval_prompts": [prompt.model_dump() for prompt in review.approval_prompts],
		"operation_evaluations": [evaluation.model_dump() for evaluation in review.operation_evaluations],
		"queue": [item.model_dump() for item in review.queue],
	}


def summarize_execution_approval_result(result):
	result = ExecutionApprovalResult.model_validate(result)
	return {
		"plan_id": result.plan_id,
		"status": result.status,
		"approved_group_ids": result.approved_group_ids,
		"rejected_group_ids": result.rejected_group_ids,
		"missing_group_ids": result.missing_group_ids,
		"invalid_approval_reasons": result.invalid_approval_reasons,
		"ready_operation_ids": result.ready_operation_ids,
		"waiting_operation_ids": result.waiting_operation_ids,
		"blocked_operation_ids": result.blocked_operation_ids,
		"queue": [item.model_dump() for item in result.queue],
	}


def summarize_execution_sync_report(report):
	report = ExecutionSyncReport.model_validate(report)
	return {
		"plan_id": report.plan_id,
		"status": report.status,
		"message": report.message,
		"executed_operation_ids": report.executed_operation_ids,
		"skipped_operation_ids": report.skipped_operation_ids,
		"failed_operation_ids": report.failed_operation_ids,
		"results": [result.model_dump() for result in report.results],
	}

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
		f"\n\nCurrent datetime:\n{_now().isoformat()}"
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
		review_prompt = (
			f"Original input:\n{state.input.model_dump_json()}"
			f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
			f"\n\nCurrent datetime:\n{_now().isoformat()}"
			f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
			f"\n\nClarification questions proposed:\n{result.output.model_dump_json()}"
		)
		review = await get_assumption_review_agent().run(
			review_prompt,
			deps=state,
			usage=ctx.usage,
			usage_limits=USAGE_LIMITS,
		)
		state.assumption_review = review.output
		state.assumption_notifications.extend(build_assumption_notifications(review.output))
		if review.output.remaining_questions:
			state.user_clarification = assumption_review_to_user_clarification(review.output)
			state.stage = "waiting_for_user"
			return state.user_clarification

		state.clarification = assumption_review_to_clarification(review.output)
		state.user_clarification = None
		state.stage = "route_selection"
		return state.clarification

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
					"discover_doctype_relationships",
					"resolve_date_range",
					"resolve_relative_datetime",
					"query_actions",
					"get_action_context",
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


async def select_route(ctx: RunContext[OrchestrationState]):
	"""Choose the route, or return the route question that blocks safe selection."""
	state = ctx.deps
	if state.stage != "route_selection":
		raise ModelRetry("select_route is only available during route_selection")
	if not state.clarification:
		raise ModelRetry("Clarification must finish before route selection")
	prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nClarification:\n{state.clarification.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		f"\n\nCurrent orchestration update:\n{ctx.prompt}"
	)
	result = await get_route_selection_agent().run(
		prompt,
		deps=state,
		usage=ctx.usage,
		usage_limits=USAGE_LIMITS,
	)
	state.route_selection = result.output
	chosen_route = next(
		route for route in result.output.routes if route.route_id == result.output.chosen_route_id
	)
	if chosen_route.outcome_type == "ask_user":
		state.user_clarification = route_selection_to_user_clarification(result.output)
		state.stage = "waiting_for_user"
		return state.user_clarification

	state.stage = "implementation"
	return result.output


async def design_implementation(ctx: RunContext[OrchestrationState]):
	"""Convert the selected route into atomic execution-bus actions."""
	state = ctx.deps
	if state.stage != "implementation":
		raise ModelRetry("design_implementation is only available during implementation")
	if not state.clarification or not state.route_selection:
		raise ModelRetry("Clarification and route selection must finish before implementation design")

	chosen_route = next(
		route for route in state.route_selection.routes if route.route_id == state.route_selection.chosen_route_id
	)
	if should_use_action_blueprint_station(state):
		blueprint_result = await get_action_blueprint_agent().run(
			build_action_blueprint_prompt(state, chosen_route),
			deps=state,
			usage=ctx.usage,
			usage_limits=USAGE_LIMITS,
		)
		if isinstance(blueprint_result.output, UserClarification):
			state.user_clarification = blueprint_result.output
			state.stage = "waiting_for_user"
			return blueprint_result.output
		state.action_design = action_implementation_design_from_blueprint(state.input.input, blueprint_result.output)
		state.execution_plan = compile_execution_plan(state)
		state.stage = "execution"
		return state.execution_plan
	prompt = (
		f"Original input:\n{state.input.model_dump_json()}"
		f"\n\nClarification:\n{state.clarification.model_dump_json()}"
		f"\n\nChosen route:\n{chosen_route.model_dump_json()}"
		f"\n\nRoute selection:\n{state.route_selection.model_dump_json()}"
		f"\n\nSystem context:\n{to_jsonable_python(SYSTEM_CONTEXT)}"
		f"\n\nCurrent datetime:\n{_now().isoformat()}"
		f"\n\nInformation already collected:\n{to_jsonable_python(state.information)}"
		f"\n\nExecution bus contract:\nReturn operations, not actions. "
		f"Each operation needs operation_type, operation_family, operation_id, decision_id, description, and operation-specific input. "
		f"Use doctype.create/update/delete for DocType records. Other families are report, dashboard, scheduler, notification, and external."
		f"\n\nCurrent orchestration update:\n{ctx.prompt}"
	)
	result = await get_action_design_agent().run(
		prompt,
		deps=state,
		usage=ctx.usage,
		usage_limits=USAGE_LIMITS,
	)

	if isinstance(result.output, UserClarification):
		state.user_clarification = result.output
		state.stage = "waiting_for_user"
		return result.output

	state.action_design = result.output
	normalize_action_design(state.action_design, chosen_route, state)
	state.execution_plan = compile_execution_plan(state)
	state.stage = "execution"
	return state.execution_plan


def review_outcome(state):
	# Returns whether to complete, monitor, repair, or revert.
	pass


def normalize_action_design(action_design, chosen_route, state=None):
	for operation in action_design.operations:
		if isinstance(operation, CreateRecord):
			normalize_operation_fields(operation.fields)
			if operation.doctype == "Action" and chosen_route.outcome_type == "create" and "calendar" in chosen_route.description.lower():
				operation.fields["event"] = True
			normalize_doctype_operation_fields(operation, chosen_route, state)
		elif isinstance(operation, UpdateRecord):
			operation.expected_modified = _coerce_datetime(operation.expected_modified)
			normalize_operation_fields(operation.fields)
			normalize_doctype_operation_fields(operation, chosen_route, state)
		elif isinstance(operation, DeleteRecord) and operation.expected_modified:
			operation.expected_modified = _coerce_datetime(operation.expected_modified)
	return action_design


def normalize_operation_fields(fields):
	for fieldname in ("start_date", "end_date", "reminder"):
		if fieldname in fields and fields[fieldname] is not None:
			fields[fieldname] = _coerce_datetime(fields[fieldname]).isoformat()
	return fields


def validate_doctype_operation_fields(operation):
	meta = _get_sync_meta(operation.doctype)
	writable_fields = {
		field.fieldname
		for field in meta.fields
		if _is_real_doctype_field(field) and _is_writable_field(field)
	}
	invalid_fields = set(operation.fields) - writable_fields
	if invalid_fields:
		raise ValueError(f"{operation.doctype} operation contains fields that cannot be written: {sorted(invalid_fields)}")

	if isinstance(operation, CreateRecord):
		missing_required = [
			field.fieldname
			for field in meta.fields
			if bool(field.reqd) and _is_writable_field(field) and field.fieldname not in operation.fields
		]
		if missing_required:
			raise ValueError(f"{operation.doctype} create operation is missing required fields: {missing_required}")
	return operation


def normalize_doctype_operation_fields(operation, chosen_route, state=None):
	meta = _get_readable_meta(operation.doctype)
	allowed_fields = {
		field.fieldname: field
		for field in meta.fields
		if _is_real_doctype_field(field) and _is_writable_field(field)
	}
	operation.fields = {
		fieldname: value
		for fieldname, value in operation.fields.items()
		if fieldname in allowed_fields and value is not None
	}

	if isinstance(operation, CreateRecord):
		for field in meta.fields:
			if bool(field.reqd) and _is_writable_field(field) and field.fieldname not in operation.fields and field.default is not None:
				operation.fields[field.fieldname] = field.default

	if operation.doctype == "Action":
		normalize_action_operation_fields(operation, chosen_route, state)

	validate_doctype_operation_fields(operation)
	return operation


def normalize_action_operation_fields(operation, chosen_route, state=None):
	fields = operation.fields
	route_text = f"{chosen_route.description} {chosen_route.expected_outcome}".lower()
	if isinstance(operation, CreateRecord) and any(term in route_text for term in ("calendar", "event")):
		fields["event"] = True
		fields.setdefault("todo", False)

	if "description" not in fields and _doctype_has_writable_field("Action", "description"):
		description = build_action_description(operation, chosen_route, state)
		if description:
			fields["description"] = description

	if "status" in fields and fields["status"] is None:
		del fields["status"]
	return operation


def _doctype_has_writable_field(doctype, fieldname):
	meta = _get_readable_meta(doctype)
	return any(field.fieldname == fieldname and _is_writable_field(field) for field in meta.fields)


def build_action_description(operation, chosen_route, state=None):
	fields = operation.fields
	parts = []
	action_name = fields.get("action_name")
	if action_name:
		parts.append(str(action_name))
	if fields.get("start_date") and fields.get("end_date"):
		parts.append(f"Scheduled from {fields['start_date']} to {fields['end_date']}.")
	elif fields.get("start_date"):
		parts.append(f"Scheduled for {fields['start_date']}.")
	if state and state.clarification:
		parts.append(f"Created from request: {state.clarification.problem.goal}")
	else:
		parts.append(chosen_route.expected_outcome)
	return " ".join(part for part in parts if part).strip()

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


def _get_sync_meta(doctype):
	import frappe

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


def _filter_fieldnames(filters):
	if not filters:
		return []

	fieldnames = []
	for item in filters:
		if isinstance(filters, dict):
			fieldnames.append(item)
		elif isinstance(item, (list, tuple)):
			if len(item) >= 4:
				fieldnames.append(item[1])
			elif item:
				fieldnames.append(item[0])
	return fieldnames


def _validate_filters(meta, filters):
	filters = filters or {}
	_validate_fields(meta, _filter_fieldnames(filters))
	return filters


def _validate_or_filters(meta, or_filters):
	or_filters = or_filters or []
	_validate_fields(meta, _filter_fieldnames(or_filters))
	return or_filters


def _validate_order_by(meta, order_by):
	if not order_by:
		return None

	parts = order_by.split()
	if len(parts) > 2 or (len(parts) == 2 and parts[1].lower() not in {"asc", "desc"}):
		raise ValueError("order_by must contain one field and an optional asc or desc")
	_validate_fields(meta, [parts[0]])
	return order_by


def _is_real_doctype_field(field):
	return field.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}


def _is_writable_field(field):
	return bool(field.fieldname) and not bool(field.read_only) and field.fieldname not in STANDARD_FIELDS


def _system_field(field):
	return SystemField(
		fieldname=field.fieldname,
		label=field.label,
		fieldtype=field.fieldtype,
		options=field.options,
		required=bool(field.reqd),
		read_only=bool(field.read_only),
		default=field.default,
		depends_on=field.depends_on,
	)


def _dedupe_system_fields(fields):
	seen = set()
	unique_fields = []
	for field in fields:
		if field.fieldname in seen:
			continue
		seen.add(field.fieldname)
		unique_fields.append(field)
	return unique_fields


def _dedupe_names(names):
	seen = set()
	unique_names = []
	for name in names:
		if name in seen:
			continue
		seen.add(name)
		unique_names.append(name)
	return unique_names


def _field_should_be_avoided_for_goal(field, goal_text):
	fieldname = field.fieldname or ""
	label = (field.label or "").lower()
	planning_keywords = {
		"optimistic_time",
		"most_likely_time",
		"pesimistic_time",
		"expected_time",
		"variance",
		"standard_deviance",
		"truth_claims",
		"witg",
		"witnotg",
		"wfwis",
		"dihtk",
		"witkin",
		"hciotkn",
		"watba",
		"wats",
	}
	if fieldname in {"lft", "rgt", "old_parent", "full_day"}:
		return True
	if fieldname in planning_keywords and not any(term in goal_text for term in ("plan", "goal", "pert", "knowledge", "state")):
		return True
	if "planning" in label and "plan" not in goal_text:
		return True
	if field.fieldtype == "Table" and fieldname not in goal_text:
		return True
	return False


def _field_is_relevant_for_goal(doctype, field, goal_text, known_values):
	fieldname = field.fieldname
	label = (field.label or "").lower()
	if fieldname in known_values and known_values[fieldname] is not None:
		return True
	if fieldname in goal_text or (label and label in goal_text):
		return True
	if doctype == "Action":
		if any(term in goal_text for term in ("calendar", "event", "meeting", "test", "exam", "appointment")):
			return fieldname in {"action_name", "description", "start_date", "end_date", "event", "color", "status", "category"}
		if any(term in goal_text for term in ("todo", "task", "remind", "reminder")):
			return fieldname in {"action_name", "description", "start_date", "end_date", "todo", "reminder", "reminder_type", "status", "category"}
		if any(term in goal_text for term in ("parent", "under", "allocate", "category", "study", "university")):
			return fieldname in {"parent_action", "ancestor", "category", "description"}
	return False


def _field_guidance(doctype, field, goal_text):
	fieldname = field.fieldname
	if doctype == "Action" and fieldname == "description":
		return "Fill with a concise human-readable summary of the user's intent and useful derived context."
	if doctype == "Action" and fieldname in {"parent_action", "ancestor"}:
		return "For same-plan tree creation, use an earlier parent operation_id. The execution bus resolves it to the created record name. For existing parents, use the real record id."
	if field.fieldtype == "Link" and field.options == doctype:
		return "For same-plan parent/tree links, use an earlier parent operation_id. For existing parents, use the real record id."
	if doctype == "Action" and fieldname == "category":
		return "Use only when a matching existing category record has been found or the route has strong evidence."
	if field.fieldtype == "Link":
		return "Use an existing linked record id or an earlier same-plan operation_id for a record this plan creates. Do not invent linked records."
	if field.fieldtype == "Select" and field.options:
		return f"Use one of: {field.options}."
	if field.fieldtype == "Check":
		return "Use true or false only when this classification is part of the route."
	return "Fill when the value follows from the user request, route, or collected system facts."


def _system_source_allowed(ctx):
	deps = ctx.get("deps") if isinstance(ctx, dict) else ctx.deps
	source_scope = deps.get("source_scope") if isinstance(deps, dict) else getattr(deps, "source_scope", "system")
	if source_scope == "web":
		raise ModelRetry("This request only permits web sources")


def _json_safe(value):
	return json.loads(json.dumps(value, default=str))


def _local_timezone():
	timezone_name = os.getenv("KRATIUM_TIMEZONE")
	if not timezone_name:
		try:
			import frappe

			timezone_name = frappe.conf.get("time_zone")
		except Exception:
			pass
	return ZoneInfo(timezone_name or "Africa/Johannesburg")


def _combine_local(date_value, time_value):
	return datetime.combine(date_value, time_value, tzinfo=_local_timezone())


def _now():
	return datetime.now(_local_timezone())


def _day_bounds(value):
	return (
		_combine_local(value.date(), time.min),
		_combine_local(value.date(), time.max),
	)


def _week_bounds(value):
	start_date = (value - timedelta(days=value.weekday())).date()
	end_date = start_date + timedelta(days=6)
	return (
		_combine_local(start_date, time.min),
		_combine_local(end_date, time.max),
	)


def _month_bounds(value):
	start_date = value.replace(day=1).date()
	next_month = (value.replace(day=28) + timedelta(days=4)).replace(day=1)
	end_date = (next_month - timedelta(days=1)).date()
	return (
		_combine_local(start_date, time.min),
		_combine_local(end_date, time.max),
	)


def _action_summary_fields():
	return [
		"name",
		"action_name",
		"start_date",
		"end_date",
		"status",
		"completed",
		"event",
		"todo",
		"routine",
		"is_group",
		"parent_action",
		"ancestor",
		"category",
		"modified",
	]


def _coerce_datetime(value):
	if value is None or isinstance(value, datetime):
		if value and value.tzinfo is None:
			return value.replace(tzinfo=_local_timezone())
		if value:
			return value.replace(tzinfo=_local_timezone())
		return value
	if isinstance(value, str):
		cleaned_value = value.replace("Z", "+00:00")
		for parser in (
			datetime.fromisoformat,
			lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
			lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M"),
			lambda text: datetime.strptime(text, "%Y-%m-%d"),
		):
			try:
				parsed_value = parser(cleaned_value)
				if parsed_value.tzinfo is None:
					return parsed_value.replace(tzinfo=_local_timezone())
				return parsed_value.replace(tzinfo=_local_timezone())
			except ValueError:
				pass
	raise ValueError(f"Unsupported datetime value: {value}")


def _record_action_context(doc):
	data = doc.as_dict()
	record = {field: data.get(field) for field in _action_summary_fields()}
	record["dependencies"] = [
		{"dependant_on": row.dependant_on}
		for row in data.get("dependancies", [])
		if row.get("dependant_on")
	]
	record["constraints"] = [
		{
			"constrining_action": row.constrining_action,
			"constraint": row.constraint,
		}
		for row in data.get("constraints", [])
		if row.get("constrining_action") or row.get("constraint")
	]
	return record


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
	return build_doctype_description(doctype)


def describe_doctype_for_orchestration(ctx: RunContext[OrchestrationState], doctype: str):
	"""Return DocType fields directly to a stage agent designing operations."""
	return build_doctype_description(doctype)


def build_doctype_description(doctype: str):
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
				default=field.default,
				depends_on=field.depends_on,
			)
			for field in meta.fields
			if field.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
		],
	)


def plan_doctype_fields_for_operation(
	ctx: RunContext[OrchestrationState],
	doctype: str,
	operation_type: Literal["doctype.create", "doctype.update"],
	goal: str,
	known_values: dict[str, Any] | None = None,
):
	"""Plan which live DocType fields belong in one atomic operation."""
	meta = _get_readable_meta(doctype)
	known_values = known_values or {}
	goal_text = f"{goal} {json.dumps(known_values, default=str)}".lower()

	fields = [field for field in meta.fields if _is_real_doctype_field(field)]
	required_fields = [field.fieldname for field in fields if bool(field.reqd) and _is_writable_field(field)]
	relevant_fields = []
	avoid_fields = []
	field_types = {}
	select_options = {}
	field_guidance = {}
	system_notes = []

	for field in fields:
		fieldname = field.fieldname
		if not _is_writable_field(field):
			avoid_fields.append(fieldname)
			continue

		if _field_should_be_avoided_for_goal(field, goal_text):
			avoid_fields.append(fieldname)
			continue

		if bool(field.reqd) or _field_is_relevant_for_goal(doctype, field, goal_text, known_values):
			relevant_fields.append(fieldname)
			field_types[fieldname] = field.fieldtype
			if field.fieldtype == "Select" and field.options:
				select_options[fieldname] = [option for option in field.options.split("\n") if option]
			field_guidance[fieldname] = _field_guidance(doctype, field, goal_text)

	if doctype == "Action":
		system_notes.append(
			"Action calendar events should normally fill action_name, start_date, end_date, event, and description."
		)
		system_notes.append(
			"Action PERT, goal-planning, state-planning, dependency, and tree fields are not part of a simple event unless the route asks for them."
		)
		system_notes.append(
			"For same-plan Action trees, create each parent before its children and set each child parent_action to the parent operation_id."
		)

	return OperationFieldPlan(
		doctype=doctype,
		operation_type=operation_type,
		required_fields=required_fields,
		relevant_fields=_dedupe_names(relevant_fields),
		avoid_fields=_dedupe_names(avoid_fields),
		field_types=field_types,
		select_options=select_options,
		field_guidance=field_guidance,
		system_notes=system_notes,
	)


def discover_doctype_relationships_for_orchestration(ctx: RunContext[OrchestrationState], doctype: str):
	"""Return DocType relationships directly to a stage agent designing operations."""
	return build_doctype_relationships(doctype)


def discover_doctype_relationships(ctx: RunContext[InformationRequest], doctype: str):
	"""Return outgoing and incoming Link/Table relationships for a readable DocType."""
	_system_source_allowed(ctx)
	return build_doctype_relationships(doctype)


def build_doctype_relationships(doctype: str):
	meta = _get_readable_meta(doctype)
	outgoing_links = []
	incoming_links = []

	for field in meta.fields:
		if field.fieldtype in {"Link", "Table"} and field.options:
			outgoing_links.append(LinkField(
				fieldname=field.fieldname,
				label=field.label,
				fieldtype=field.fieldtype,
				options=field.options,
				direction="outgoing",
				doctypes=[field.options] if field.options in AI_READABLE_DOCTYPES else [],
			))

	for candidate in sorted(AI_READABLE_DOCTYPES):
		candidate_meta = _get_readable_meta(candidate)
		for field in candidate_meta.fields:
			if field.fieldtype in {"Link", "Table"} and field.options == doctype:
				incoming_links.append(LinkField(
					fieldname=field.fieldname,
					label=field.label,
					fieldtype=field.fieldtype,
					options=doctype,
					direction="incoming",
					doctypes=[candidate],
				))

	return RelationshipMap(
		doctype=doctype,
		outgoing_links=outgoing_links,
		incoming_links=incoming_links,
	)


def resolve_date_range(
	ctx: RunContext[InformationRequest],
	period: Literal["today", "tomorrow", "yesterday", "this_week", "next_week", "this_month", "next_month"],
):
	"""Resolve common calendar phrases into exact datetime bounds."""
	_system_source_allowed(ctx)
	now = _now()
	if period == "today":
		start, end = _day_bounds(now)
	elif period == "tomorrow":
		start, end = _day_bounds(now + timedelta(days=1))
	elif period == "yesterday":
		start, end = _day_bounds(now - timedelta(days=1))
	elif period == "this_week":
		start, end = _week_bounds(now)
	elif period == "next_week":
		start, end = _week_bounds(now + timedelta(days=7))
	elif period == "this_month":
		start, end = _month_bounds(now)
	else:
		start, end = _month_bounds((now.replace(day=28) + timedelta(days=4)))

	return DateRangeResult(
		label=period,
		start=start,
		end=end,
		timezone=now.tzname(),
	)


def resolve_relative_datetime(
	ctx: RunContext[InformationRequest],
	phrase: Literal[
		"today",
		"tomorrow",
		"monday",
		"tuesday",
		"wednesday",
		"thursday",
		"friday",
		"saturday",
		"sunday",
		"next_monday",
		"next_tuesday",
		"next_wednesday",
		"next_thursday",
		"next_friday",
		"next_saturday",
		"next_sunday",
	],
	hour: int = 9,
	minute: int = 0,
):
	"""Resolve a relative day phrase into one exact datetime."""
	_system_source_allowed(ctx)
	if not 0 <= hour <= 23 or not 0 <= minute <= 59:
		raise ValueError("hour and minute must form a valid time")

	now = _now()
	phrase_value = phrase.lower()
	if phrase_value == "today":
		date_value = now.date()
	elif phrase_value == "tomorrow":
		date_value = (now + timedelta(days=1)).date()
	else:
		day_names = {
			"monday": 0,
			"tuesday": 1,
			"wednesday": 2,
			"thursday": 3,
			"friday": 4,
			"saturday": 5,
			"sunday": 6,
		}
		force_next_week = phrase_value.startswith("next_")
		day_name = phrase_value.removeprefix("next_")
		days_ahead = (day_names[day_name] - now.weekday()) % 7
		if days_ahead == 0 or force_next_week:
			days_ahead += 7
		date_value = (now + timedelta(days=days_ahead)).date()

	return DateTimeResult(
		label=phrase,
		value=_combine_local(date_value, time(hour, minute)),
		timezone=now.tzname(),
	)


def query_actions(
	ctx: RunContext[InformationRequest],
	start: str | None = None,
	end: str | None = None,
	calendar_only: bool = False,
	parent_action: str | None = None,
	ancestor: str | None = None,
	category: str | None = None,
	status: Literal["Upcoming", "In Progress", "Completed"] | None = None,
	completed: bool | None = None,
	text: str | None = None,
	limit: int = 50,
):
	"""Query Action records with common calendar, hierarchy, category, and lifecycle filters."""
	import frappe

	_system_source_allowed(ctx)
	meta = _get_readable_meta("Action")
	start = _coerce_datetime(start)
	end = _coerce_datetime(end)
	if start and end and end < start:
		raise ValueError("end cannot be before start")

	filters = []
	if calendar_only:
		filters.append(["Action", "event", "=", 1])
	if parent_action:
		filters.append(["Action", "parent_action", "=", parent_action])
	if ancestor:
		filters.append(["Action", "ancestor", "=", ancestor])
	if category:
		filters.append(["Action", "category", "=", category])
	if status:
		filters.append(["Action", "status", "=", status])
	if completed is not None:
		filters.append(["Action", "completed", "=", int(completed)])
	if start and end:
		filters.extend([
			["Action", "start_date", "<=", end],
			["Action", "end_date", ">=", start],
		])
	elif start:
		filters.append(["Action", "start_date", ">=", start])
	elif end:
		filters.append(["Action", "end_date", "<=", end])

	_validate_filters(meta, filters)
	limit = max(1, min(limit, 100))
	or_filters = None
	if text:
		or_filters = [
			["Action", "action_name", "like", f"%{text}%"],
			["Action", "description", "like", f"%{text}%"],
		]
		_validate_or_filters(meta, or_filters)

	records = frappe.get_list(
		"Action",
		filters=filters,
		or_filters=or_filters,
		fields=_action_summary_fields(),
		order_by="start_date asc",
		limit_page_length=limit + 1,
	)
	visible_records = records[:limit]
	return ActionLookupResult(
		filters=_json_safe(filters),
		records=_json_safe(visible_records),
		count=len(visible_records),
		limit=limit,
		has_more=len(records) > limit,
		note="Calendar records are Action records where event is enabled." if calendar_only else None,
	)


def get_action_context(ctx: RunContext[InformationRequest], action_id: str):
	"""Return one Action plus direct hierarchy and dependency context."""
	import frappe

	_system_source_allowed(ctx)
	_get_readable_meta("Action")
	doc = frappe.get_doc("Action", action_id)
	doc.check_permission("read")
	children = frappe.get_list(
		"Action",
		filters={"parent_action": action_id},
		fields=_action_summary_fields(),
		order_by="start_date asc",
		limit_page_length=50,
	)
	return {
		"doctype": "Action",
		"name": action_id,
		"record": _json_safe(_record_action_context(doc)),
		"children": _json_safe(children),
		"child_count": len(children),
	}


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
		limit_page_length=limit + 1,
	)
	visible_records = records[:limit]
	return SystemRecordResult(
		doctype=doctype,
		filters=_json_safe(filters),
		records=_json_safe(visible_records),
		count=len(visible_records),
		limit=limit,
		offset=offset,
		has_more=len(records) > limit,
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
		limit_page_length=limit + 1,
	)
	visible_records = records[:limit]
	return SystemRecordResult(
		doctype=doctype,
		filters=_json_safe(filters),
		records=_json_safe(visible_records),
		count=len(visible_records),
		limit=limit,
		has_more=len(records) > limit,
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
			f"{result.get('title', 'Untitled')}: {(result.get('body') or '')[:500]}"
			for result in results[:5]
		),
		sources=[
			WebSource(
				title=result.get("title") or result["href"],
				url=result["href"],
			)
			for result in results[:5]
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
		content=content[:12_000],
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
