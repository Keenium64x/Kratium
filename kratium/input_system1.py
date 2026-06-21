from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import frappe
from frappe.utils import get_datetime, now_datetime
from pydantic import BaseModel, Field, ValidationError


# =============================================================================
# Schema
# =============================================================================


MutationOperation = Literal["create", "update", "delete"]
ReadOperation = Literal["read"]

ActionLayer = Literal["action", "todo", "event"]
ActionColor = Literal["amber", "violet", "pink", "cyan", "blue", "orange", "green"]
ActionStatus = Literal["Upcoming", "In Progress", "Completed"]
ActionPlanningType = Literal["custom", "cusin", "cusout", "BaseAction"]
ReminderType = Literal["Once", "Until Completion", "Before Completion", "Snooze"]
ConstraintType = Literal["FS", "SS", "FF", "SF"]

ReadTarget = Literal["action", "action_category", "action_time_entry"]
SearchTarget = Literal["action", "action_category"]
AIResponseType = Literal["search", "final_schema"]
FinalSchemaType = Literal["mutation", "read"]
SearchPurpose = Literal[
	"assign_parent_action",
	"assign_dependency",
	"assign_category",
	"read_actions",
	"read_categories",
	"general",
]
SearchScale = Literal["day", "week", "month", "quarter", "year", "any"]


class ActionDependencyInput(BaseModel):
	action: str | None = None
	batch_ref: str | None = None
	reason: str | None = None


class ActionConstraintInput(BaseModel):
	action: str
	constraint: ConstraintType = "FS"
	reason: str | None = None


class ActionMutationInput(BaseModel):
	operation: MutationOperation = "create"
	layer: ActionLayer = "action"

	batch_ref: str | None = None
	name: str | None = None
	title: str | None = None
	description: str | None = None
	raw_text: str | None = None

	start_date: str | None = None
	end_date: str | None = None
	deadline: str | None = None
	estimated_hours: float | None = None
	color: ActionColor | None = None

	ancestor: str | None = None
	parent_action: str | None = None
	is_group: bool | None = None

	status: ActionStatus | None = None
	completed: bool | None = None
	starred: bool | None = None
	full_day: bool | None = None
	routine: bool | None = None

	reminder: str | None = None
	reminder_type: ReminderType | None = None
	reminder_interval: str | None = None

	milestone: bool | None = None
	milestone_action: str | None = None
	dependencies: list[ActionDependencyInput] = Field(default_factory=list)
	constraints: list[ActionConstraintInput] = Field(default_factory=list)

	category: str | None = None
	category_reason: str | None = None
	category_confidence: float | None = None
	needs_category_assignment: bool = True


	tags: list[str] = Field(default_factory=list)


class ActionReadInput(BaseModel):
	operation: ReadOperation = "read"
	target: ReadTarget = "action"
	name: str | None = None
	filters: dict[str, Any] = Field(default_factory=dict)
	fields: list[str] = Field(default_factory=lambda: ["name"])
	limit: int = 20
	order_by: str | None = None
	search: "SearchRequest | None" = None


class SearchRequest(BaseModel):
	target: SearchTarget
	purpose: SearchPurpose = "general"
	query: str | None = None
	description_context: str | None = None

	scale: SearchScale = "any"
	date_start: str | None = None
	date_end: str | None = None

	parent_action: str | None = None
	ancestor: str | None = None
	parent_action_category: str | None = None

	limit: int = 10
	previous_results: list[dict[str, Any]] = Field(default_factory=list)
	previous_reasoning: str | None = None


class SearchResult(BaseModel):
	request: SearchRequest
	results: list[dict[str, Any]]


FinishedCommand = ActionMutationInput | ActionReadInput
FinishedInput = FinishedCommand | list[FinishedCommand]


class ParseResult(BaseModel):
	success: bool
	data: FinishedInput | None = None
	error: str | None = None


class AIModelResponse(BaseModel):
	type: AIResponseType
	data: dict[str, Any] | list[dict[str, Any]]
	schema: FinalSchemaType | None = None
	reasoning: str | None = None


# =============================================================================
# Search Boilerplate
# =============================================================================


def run_search_request(search: SearchRequest) -> SearchResult:
	results = execute_search(search)
	return SearchResult(request=search, results=results)


def execute_search(search: SearchRequest) -> list[dict[str, Any]]:
	if search.target == "action":
		return search_actions(search)

	if search.target == "action_category":
		return search_action_categories(search)

	raise ValueError(f"Unknown search target: {search.target}")


def search_actions(search: SearchRequest) -> list[dict[str, Any]]:
	filters: dict[str, Any] = {}
	or_filters = []

	if search.parent_action:
		filters["parent_action"] = search.parent_action

	if search.ancestor:
		filters["ancestor"] = search.ancestor

	if search.date_start:
		filters["start_date"] = [">=", search.date_start]

	if search.date_end:
		filters["end_date"] = ["<=", search.date_end]

	if search.purpose == "assign_parent_action":
		filters["is_group"] = 1

	if search.query:
		like_query = f"%{search.query}%"
		or_filters = [
			["Action", "name", "like", like_query],
			["Action", "action_name", "like", like_query],
			["Action", "description", "like", like_query],
			["Action", "witg", "like", like_query],
			["Action", "witnotg", "like", like_query],
		]

	return frappe.get_all(
		"Action",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"action_name",
			"description",
			"parent_action",
			"ancestor",
			"start_date",
			"end_date",
			"status",
			"is_group",
			"todo",
			"event",
			"category",
			"type",
		],
		limit_page_length=search.limit,
	)


def search_action_categories(search: SearchRequest) -> list[dict[str, Any]]:
	filters: dict[str, Any] = {}
	or_filters = []

	if search.parent_action_category:
		filters["parent_action_category"] = search.parent_action_category

	if search.query:
		like_query = f"%{search.query}%"
		or_filters = [
			["Action Category", "name", "like", like_query],
		]

	return frappe.get_all(
		"Action Category",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"parent_action_category",
			"is_group",
			"action",
		],
		limit_page_length=search.limit,
	)


# =============================================================================
# Entry Function
# =============================================================================


def process_input(raw_text: str) -> dict[str, Any]:
	finished_schema = parse_input(raw_text)
	return sync_finished_schema_to_frappe(finished_schema)


def preview_input(raw_text: str) -> dict[str, Any] | list[dict[str, Any]]:
	finished_schema = parse_input(raw_text)
	return dump_finished_input(finished_schema)


def parse_input(raw_text: str) -> FinishedInput:
	normalized_text = normalize_text(raw_text)
	ai_result = parse_with_ai(normalized_text)

	if ai_result.success and ai_result.data:
		return ai_result.data

	raise ValueError(ai_result.error or "Could not parse input")


# =============================================================================
# Sync Finished Schema To Frappe
# =============================================================================


def sync_finished_schema_to_frappe(schema: FinishedInput) -> dict[str, Any]:
	if isinstance(schema, list):
		if any(isinstance(command, ActionReadInput) for command in schema):
			raise ValueError("Batch input currently supports mutation commands only")

		results = []
		created_commands: dict[str, dict[str, Any]] = {}

		try:
			for command in schema:
				command = resolve_batch_references(command, created_commands)
				result = sync_action_to_frappe(command, commit=False)
				results.append(result)

				if command.batch_ref and result["operation"] == "create":
					created_commands[command.batch_ref] = {
						"name": result["name"],
						"start_date": command.start_date,
						"end_date": command.end_date or command.deadline,
					}
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			raise

		return {
			"operation": "batch",
			"count": len(results),
			"results": results,
		}

	if isinstance(schema, ActionReadInput):
		return read_from_frappe(schema)

	return sync_action_to_frappe(schema)


def sync_action_to_frappe(schema: ActionMutationInput, commit: bool = True) -> dict[str, Any]:
	data = dump_schema(schema)

	if data["operation"] == "create":
		if not data.get("title"):
			raise ValueError("title is required to create an Action")
		if not data.get("start_date") or not (data.get("end_date") or data.get("deadline")):
			raise ValueError("start_date and end_date or deadline are required to create an Action")

		doc = frappe.get_doc(clean_doc_data(map_schema_to_action_doc(data)))
		doc.insert()
		if commit:
			frappe.db.commit()
		return {"operation": "create", "doctype": doc.doctype, "name": doc.name}

	if data["operation"] == "update":
		if not data["name"]:
			raise ValueError("name is required to update an Action")

		doc = frappe.get_doc("Action", data["name"])
		for fieldname, value in clean_doc_data(map_schema_to_action_doc(data)).items():
			if fieldname != "doctype":
				setattr(doc, fieldname, value)
		doc.save()
		if commit:
			frappe.db.commit()
		return {"operation": "update", "doctype": doc.doctype, "name": doc.name}

	if data["operation"] == "delete":
		if not data["name"]:
			raise ValueError("name is required to delete an Action")

		frappe.delete_doc("Action", data["name"])
		if commit:
			frappe.db.commit()
		return {"operation": "delete", "doctype": "Action", "name": data["name"]}

	raise ValueError(f"Unknown operation: {data['operation']}")


def read_from_frappe(schema: ActionReadInput) -> dict[str, Any]:
	data = dump_schema(schema)

	if data["name"]:
		doc = frappe.get_doc(to_doctype(data["target"]), data["name"])
		return {"operation": "read", "item": doc.as_dict()}

	items = frappe.get_all(
		to_doctype(data["target"]),
		filters=data["filters"],
		fields=data["fields"],
		limit_page_length=data["limit"],
		order_by=data["order_by"],
	)

	return {"operation": "read", "items": items}


def map_schema_to_action_doc(data: dict[str, Any]) -> dict[str, Any]:
	return {
		"doctype": "Action",
		"action_name": data.get("title"),
		"description": data.get("description"),
		"start_date": to_frappe_datetime(data.get("start_date")),
		"end_date": to_frappe_datetime(data.get("end_date") or data.get("deadline")),
		"estimated_hours": data.get("estimated_hours"),
		"color": data.get("color"),
		"ancestor": data.get("ancestor"),
		"parent_action": data.get("parent_action"),
		"is_group": data.get("is_group"),
		"status": data.get("status"),
		"completed": data.get("completed"),
		"starred": data.get("starred"),
		"full_day": data.get("full_day"),
		"routine": data.get("routine"),
		"reminder": to_frappe_datetime(data.get("reminder")),
		"reminder_type": data.get("reminder_type"),
		"reminder_interval": data.get("reminder_interval"),
		"milestone": data.get("milestone"),
		"milestone_action": data.get("milestone_action"),
		"todo": 1 if data.get("layer") == "todo" else None,
		"event": 1 if data.get("layer") == "event" else None,
		"type": data.get("planning_type"),
		"basegoal": data.get("basegoal"),
		"goal": data.get("goal"),
		"category": data.get("category"),
		"dependancies": [
			{"dependant_on": dependency["action"]}
			for dependency in data.get("dependencies", [])
		],
		"constraints": [
			{"constrining_action": constraint["action"], "constraint": constraint["constraint"]}
			for constraint in data.get("constraints", [])
		],
	}


def to_frappe_datetime(value: str | None) -> Any:
	if not value:
		return None
	return get_datetime(value)


def clean_doc_data(data: dict[str, Any]) -> dict[str, Any]:
	return {
		fieldname: value
		for fieldname, value in data.items()
		if value not in (None, "", [])
	}


# =============================================================================
# Normalization
# =============================================================================


def normalize_text(raw_text: str) -> str:
	return " ".join(raw_text.strip().split())


# =============================================================================
# Regex / Command Language Parser
# =============================================================================


def parse_with_regex_language(text: str) -> ParseResult:
	tokens = text.split()

	if not tokens:
		return ParseResult(success=False, error="No input")

	draft = {
		"raw_text": text,
		"operation": "create",
		"layer": "action",
		"title": None,
	}

	keyword_map = {
		"by": "deadline",
		"b": "deadline",
		"before": "deadline",
		"at": "start_date",
		"from": "start_date",
		"to": "end_date",
		"until": "end_date",
		"for": "estimated_hours",
		"under": "parent_action",
		"after": "dependencies",
		"category": "category",
		"important": "importance",
		"urgent": "urgency",
		"priority": "priority",
	}

	current_field = "title"
	current_words = []

	for token in tokens:
		key = token.lower().strip(".,:;")

		if key in keyword_map:
			save_words_to_draft(draft, current_field, current_words)
			current_field = keyword_map[key]
			current_words = []
			continue

		current_words.append(token)

	save_words_to_draft(draft, current_field, current_words)

	if not draft.get("title"):
		return ParseResult(success=False, error="Regex parser could not find a title")

	return ParseResult(success=True, data=ActionMutationInput(**draft))


def save_words_to_draft(draft: dict[str, Any], field: str, words: list[str]) -> None:
	value = " ".join(words).strip()

	if not value:
		return

	if field == "dependencies":
		draft.setdefault("dependencies", []).append({"action": value})
		return

	draft[field] = value


# =============================================================================
# AI Parser Fallback
# =============================================================================


def parse_with_ai(text: str) -> ParseResult:
	context = {
		"search_history": [],
		"available_action_categories": frappe.get_all(
			"Action Category",
			fields=["name", "parent_action_category", "is_group"],
			limit_page_length=20,
		),
	}
	max_steps = 5

	for _step in range(max_steps):
		try:
			ai_response = validate_ai_response(
				call_ai_model(
					text=text,
					schemas=get_ai_schemas(),
					context=context,
				)
			)

			if ai_response.type == "search":
				search = SearchRequest(**ai_response.data)
				context["search_history"].append(dump_schema(run_search_request(search)))
				continue

			if ai_response.type == "final_schema":
				if ai_response.schema == "read":
					if isinstance(ai_response.data, list):
						return ParseResult(success=False, error="Read responses must contain one schema")
					return ParseResult(success=True, data=ActionReadInput(**ai_response.data))

				if ai_response.schema == "mutation":
					items = ai_response.data if isinstance(ai_response.data, list) else [ai_response.data]

					if not items:
						return ParseResult(success=False, error="Mutation response contained no commands")

					schemas = []
					for item in items:
						item = {
							key: value
							for key, value in item.items()
							if key not in {"type", "schema"}
						}
						schema = ActionMutationInput(**item)
						schema = normalize_action_times(schema)
						schemas.append(sanitize_action_links(schema))

					if isinstance(ai_response.data, list):
						return ParseResult(success=True, data=normalize_batch_dates(schemas))

					return ParseResult(success=True, data=schemas[0])

				return ParseResult(success=False, error="AI final_schema response must choose read or mutation")

		except NotImplementedError:
			return ParseResult(success=False, error="AI parser is not connected yet")
		except (KeyError, TypeError, ValidationError) as error:
			return ParseResult(success=False, error=str(error))

	return ParseResult(success=False, error="AI parser reached the search/refinement limit")


def call_ai_model(text: str, schemas: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
	payload = {
		"model": get_ollama_model(),
		"stream": False,
		"format": get_schema_json(AIModelResponse),
		"think": False,
		"keep_alive": "5m",
		"options": {
			"temperature": 0,
			"num_predict": 512,
		},
		"messages": [
			{
				"role": "system",
				"content": build_ai_system_prompt(schemas),
			},
			{
				"role": "user",
				"content": json.dumps(
					{
						"user_input": text,
						"context": context,
					},
					default=str,
				),
			},
		],
	}

	request = Request(
		get_ollama_url(),
		data=json.dumps(payload).encode("utf-8"),
		headers={"Content-Type": "application/json"},
		method="POST",
	)

	for attempt in range(2):
		try:
			with urlopen(request, timeout=get_ollama_timeout()) as response:
				ollama_response = json.loads(response.read().decode("utf-8"))
			break
		except HTTPError as error:
			body = error.read().decode("utf-8", errors="replace")
			if error.code == 500 and attempt == 0:
				time.sleep(2)
				continue
			raise RuntimeError(f"Ollama returned HTTP {error.code}: {body}") from error
		except URLError as error:
			raise RuntimeError(f"Could not connect to Ollama: {error}") from error
		except TimeoutError as error:
			raise RuntimeError(
				f"Ollama timed out after {get_ollama_timeout()} seconds"
			) from error

	content = ollama_response.get("message", {}).get("content")

	if not content:
		raise RuntimeError("Ollama returned an empty response")

	try:
		return extract_json_object(content)
	except json.JSONDecodeError as error:
		raise RuntimeError(f"Ollama returned invalid JSON: {content!r}") from error


# =============================================================================
# Helpers
# =============================================================================


def get_ai_schemas() -> dict[str, Any]:
	return {
		"response": {
			"type": "search | final_schema",
			"schema": "mutation | read | null",
			"data": "SearchRequest object, one ActionMutationInput object, a list of ActionMutationInput objects, or one ActionReadInput object",
		},
		"mutation": {
			"operation": "create | update | delete",
			"layer": "action | todo | event",
			"batch_ref": "short unique identifier for this command within a mutation batch, otherwise null",
			"name": "document name for update/delete, otherwise null",
			"title": "string or null",
			"description": "string or null",
			"raw_text": "original user text",
			"start_date": "YYYY-MM-DD HH:MM:SS or null",
			"end_date": "YYYY-MM-DD HH:MM:SS or null",
			"deadline": "YYYY-MM-DD HH:MM:SS or null",
			"estimated_hours": "number or null",
			"color": "amber | violet | pink | cyan | blue | orange | green | null",
			"ancestor": "existing Action name or null",
			"parent_action": "existing Action name or null",
			"is_group": "boolean or null",
			"status": "Upcoming | In Progress | Completed | null",
			"completed": "boolean or null",
			"starred": "boolean or null",
			"full_day": "boolean or null",
			"routine": "boolean or null",
			"reminder": "YYYY-MM-DD HH:MM:SS or null",
			"reminder_type": "Once | Until Completion | Before Completion | Snooze | null",
			"reminder_interval": "string or null",
			"milestone": "boolean or null",
			"milestone_action": "existing Action name or null",
			"dependencies": [{
				"action": "existing Action name or null",
				"batch_ref": "earlier command batch_ref or null",
				"reason": "string or null",
			}],
			"constraints": [{"action": "existing Action name", "constraint": "FS | SS | FF | SF"}],
			"category": "existing Action Category name or null",
			"category_reason": "string or null",
			"category_confidence": "0 to 1 or null",
			"needs_category_assignment": "boolean",
			"tags": ["string"],
		},
		"read": {
			"operation": "read",
			"target": "action | action_category | action_time_entry",
			"name": "exact document name or null",
			"filters": "Frappe filter object",
			"fields": ["field names"],
			"limit": "integer",
			"order_by": "string or null",
		},
		"search": {
			"target": "action | action_category",
			"purpose": "assign_parent_action | assign_dependency | assign_category | read_actions | read_categories | general",
			"query": "short search phrase or null",
			"description_context": "reason for the search",
			"scale": "day | week | month | quarter | year | any",
			"date_start": "YYYY-MM-DD HH:MM:SS or null",
			"date_end": "YYYY-MM-DD HH:MM:SS or null",
			"parent_action": "existing Action name or null",
			"ancestor": "existing Action name or null",
			"parent_action_category": "existing Action Category name or null",
			"limit": "1 to 10",
		},
	}


def build_ai_system_prompt(schemas: dict[str, Any]) -> str:
	return (
		"You are the Kratium input mapper. Convert the user's text into JSON only. "
		"Return exactly one JSON object matching AIModelResponse. "
		"If you need existing Action or Action Category context, return type='search' "
		"with data matching SearchRequest. After search results are provided in context, "
		"return type='final_schema' when enough information is known. "
		"For final_schema, set schema to 'mutation' or 'read' and put the matching schema in data. "
		"When the user explicitly requests multiple creates/updates/deletes, return data as a JSON array with exactly one "
		"mutation object per explicitly requested operation. Do not create inferred reminders, duplicate variants, or extra tasks. "
		"Give every mutation in a batch a short unique batch_ref. When a later command clearly depends on an earlier command "
		"in the same batch, add a dependency using that earlier batch_ref. Never use a title as an Action document name. "
		"For a single operation, return data as one object rather than an array. "
		"Omit unknown optional mutation fields instead of listing every field as null. "
		"Enrich each mutation as fully as the user's words safely allow. Always provide a concise description that explains "
		"the requested action using only information present or directly implied by the user input. Add useful tags from the "
		"user's wording. Set normal lifecycle defaults such as status='Upcoming', completed=false, is_group=false, starred=false, "
		"routine=false, and milestone=false when appropriate. Infer layer and straightforward dependencies from explicit wording "
		"such as 'after', 'then', 'follow up', or 'depends on'. Do not invent people, locations, durations, goals, dates, "
		"priorities, reminders, parents, or dependencies that are not supported by the input. "
		"Do not write prose, markdown, or explanations outside JSON. "
		"Use null for unknown optional fields. "
		"Prefer operation='create' for normal add-task commands. "
		"Use layer='todo' for tasks/to-dos, layer='event' for calendar events, and layer='action' for broader actions. "
		"Never invent Frappe document names for category, parent_action, ancestor, milestone_action, dependencies, or constraints. "
		"For create mutations, first inspect available_action_categories in context. If it is empty, set category=null and "
		"needs_category_assignment=true without searching. If it contains a clear match, use that exact category name. Otherwise "
		"request an Action Category search when no category was explicitly supplied and no category search appears in context. "
		"Choose a category only from returned context or search results. If no matching category is found, set category=null "
		"and needs_category_assignment=true. "
		"For create operations, provide both start_date and end_date. If only one time is supplied and duration is unknown, "
		"use that same datetime for both start_date and end_date. "
		f"Current local datetime is {now_datetime()}. Resolve relative dates such as today and tomorrow. "
		f"Schemas: {json.dumps(schemas, default=str)}"
	)


def get_ollama_url() -> str:
	return get_config_value("KRATIUM_OLLAMA_URL", "ollama_url", "http://localhost:11434/api/chat")


def get_ollama_base_url() -> str:
	url = get_ollama_url().rstrip("/")
	if url.endswith("/api/chat"):
		return url.removesuffix("/api/chat")
	return url


def get_ollama_model() -> str:
	return get_config_value("KRATIUM_OLLAMA_MODEL", "ollama_model", "llama3.2")


def get_ollama_timeout() -> int:
	value = get_config_value("KRATIUM_OLLAMA_TIMEOUT", "ollama_timeout", "120")
	return int(value)


def get_config_value(env_name: str, frappe_conf_name: str, default: str) -> str:
	if os.environ.get(env_name):
		return os.environ[env_name]

	try:
		value = frappe.conf.get(frappe_conf_name)
	except Exception:
		value = None

	return str(value or default)


def test_ollama_connection() -> dict[str, Any]:
	request = Request(f"{get_ollama_base_url()}/api/tags", method="GET")

	try:
		with urlopen(request, timeout=get_ollama_timeout()) as response:
			data = json.loads(response.read().decode("utf-8"))
	except URLError as error:
		raise RuntimeError(f"Could not connect to Ollama: {error}") from error

	models = [model.get("name") for model in data.get("models", [])]

	return {
		"url": get_ollama_url(),
		"selected_model": get_ollama_model(),
		"available_models": models,
		"selected_model_available": get_ollama_model() in models,
	}


def extract_json_object(text: str) -> dict[str, Any]:
	text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

	try:
		return json.loads(text)
	except json.JSONDecodeError:
		match = re.search(r"\{.*", text, flags=re.DOTALL)
		if not match:
			raise
		json_text = match.group(0)
		missing_braces = json_text.count("{") - json_text.count("}")
		if missing_braces > 0:
			json_text += "}" * missing_braces
		return json.loads(json_text)


def validate_ai_response(response: dict[str, Any]) -> AIModelResponse:
	if isinstance(response.get("response"), dict):
		response = response["response"]

	if "type" not in response and response.get("schema") in {"mutation", "read"} and "data" in response:
		response["type"] = "final_schema"

	if hasattr(AIModelResponse, "model_validate"):
		return AIModelResponse.model_validate(response)
	return AIModelResponse.parse_obj(response)


def sanitize_action_links(schema: ActionMutationInput) -> ActionMutationInput:
	data = dump_schema(schema)

	for fieldname in ["ancestor", "parent_action", "milestone_action"]:
		value = data.get(fieldname)
		if value and not frappe.db.exists("Action", value):
			data[fieldname] = None

	category = data.get("category")
	if category and not frappe.db.exists("Action Category", category):
		data["category"] = None
		data["category_reason"] = None
		data["category_confidence"] = None
		data["needs_category_assignment"] = True

	data["dependencies"] = [
		dependency
		for dependency in data.get("dependencies", [])
		if dependency.get("batch_ref")
		or (
			dependency.get("action")
			and frappe.db.exists("Action", dependency["action"])
		)
	]
	data["constraints"] = [
		constraint
		for constraint in data.get("constraints", [])
		if frappe.db.exists("Action", constraint["action"])
	]

	return ActionMutationInput(**data)


def resolve_batch_references(
	schema: ActionMutationInput,
	created_commands: dict[str, dict[str, Any]],
) -> ActionMutationInput:
	data = dump_schema(schema)
	dependency_end_dates = []

	for dependency in data.get("dependencies", []):
		batch_ref = dependency.get("batch_ref")
		if not batch_ref:
			continue

		if batch_ref not in created_commands:
			raise ValueError(f"Unknown or forward batch dependency: {batch_ref}")

		dependency_context = created_commands[batch_ref]
		dependency["action"] = dependency_context["name"]
		dependency["batch_ref"] = None
		if dependency_context.get("end_date"):
			dependency_end_dates.append(dependency_context["end_date"])

	if schema.operation == "create" and dependency_end_dates:
		dependency_end = max(dependency_end_dates)
		data["start_date"] = data.get("start_date") or dependency_end
		data["end_date"] = data.get("end_date") or data.get("deadline") or dependency_end

	return ActionMutationInput(**data)


def normalize_batch_dates(schemas: list[ActionMutationInput]) -> list[ActionMutationInput]:
	known_dates: dict[str, str] = {}
	normalized = []

	for schema in schemas:
		data = dump_schema(schema)
		dependency_end_dates = [
			known_dates[dependency["batch_ref"]]
			for dependency in data.get("dependencies", [])
			if dependency.get("batch_ref") in known_dates
		]

		if schema.operation == "create" and dependency_end_dates:
			dependency_end = max(dependency_end_dates)
			data["start_date"] = data.get("start_date") or dependency_end
			data["end_date"] = data.get("end_date") or data.get("deadline") or dependency_end

		normalized_schema = ActionMutationInput(**data)
		normalized.append(normalized_schema)

		if normalized_schema.batch_ref and (normalized_schema.end_date or normalized_schema.deadline):
			known_dates[normalized_schema.batch_ref] = normalized_schema.end_date or normalized_schema.deadline

	return normalized


def normalize_action_times(schema: ActionMutationInput) -> ActionMutationInput:
	if schema.operation != "create" or schema.layer != "todo":
		return schema

	data = dump_schema(schema)
	start_date = data.get("start_date")
	end_date = data.get("end_date")
	deadline = data.get("deadline")
	raw_text = (data.get("raw_text") or "").lower()

	due_date = deadline or start_date or end_date
	has_explicit_range = bool(
		re.search(r"\bfrom\b.+\b(?:to|until)\b", raw_text)
		or re.search(r"\bstart(?:ing)?\b.+\b(?:finish|end)\b", raw_text)
		or re.search(r"\bbetween\b.+\band\b", raw_text)
		or (
			deadline
			and start_date
			and end_date
			and end_date != deadline
		)
	)

	if not due_date or has_explicit_range:
		return schema

	due_datetime = get_datetime(due_date)
	start_datetime = due_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
	data["start_date"] = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
	data["end_date"] = due_datetime.strftime("%Y-%m-%d %H:%M:%S")
	data["deadline"] = due_datetime.strftime("%Y-%m-%d %H:%M:%S")

	return ActionMutationInput(**data)


def to_doctype(target: ReadTarget) -> str:
	if target == "action":
		return "Action"
	if target == "action_category":
		return "Action Category"
	if target == "action_time_entry":
		return "Action Time Entry"
	raise ValueError(f"Unknown read target: {target}")


def dump_schema(schema: BaseModel) -> dict[str, Any]:
	if hasattr(schema, "model_dump"):
		return schema.model_dump()
	return schema.dict()


def dump_finished_input(schema: FinishedInput) -> dict[str, Any] | list[dict[str, Any]]:
	if isinstance(schema, list):
		return [dump_schema(command) for command in schema]
	return dump_schema(schema)


def get_schema_json(schema: type[BaseModel]) -> dict[str, Any]:
	if hasattr(schema, "model_json_schema"):
		return schema.model_json_schema()
	return schema.schema()
