# Copyright (c) 2026, Keenan Solomon and contributors
# For license information, please see license.txt

import json
import traceback

import frappe
from frappe.model.document import Document

from kratium.input_system import (
	ExecutionPlan,
	ExecutionApprovalDecision,
	ExecutionPreparation,
	apply_execution_approvals,
	classify_design_scope,
	continue_cached_orchestration,
	get_cached_execution_plan,
	get_cached_execution_preparation,
	remember_execution_plan,
	remember_execution_preparation,
	preview_execution_security,
	preview_execution_security_for_plan,
	preview_reject_cached_execution,
	summarize_execution_approval_result,
	summarize_orchestration_result,
	summarize_execution_sync_report,
	sync_approved_execution,
	build_sample_create_plan,
	build_progressive_design_question_plan,
	compile_design_brief,
	next_design_question,
	prepare_execution,
	summarize_execution_preparation,
)


class AIExecutionConsole(Document):
	def validate(self):
		if not self.is_new() and self.has_value_changed("prompt") and self.status != "Draft":
			frappe.throw("Prompt is locked after processing starts. Create a new AI Execution Console request instead.")

	def before_save(self):
		self.request_title = build_request_title(self.prompt)


def build_request_title(prompt):
	text = " ".join((prompt or "").split())
	if not text:
		return "New AI request"
	return text[:77] + "..." if len(text) > 80 else text


def _json(data):
	return json.dumps(data, indent=2, default=str)


def _set_preview(doc, data):
	if data.get("security_preparation") or data.get("orchestration", {}).get("security_preparation"):
		data.setdefault("force_manual_approval", _force_manual_approval(doc))
	doc.raw_state = _json(data)
	doc.preview = _json(compact_preview(data))
	doc.readable_output = build_readable_output(data)


def _save(doc):
	if hasattr(doc, "prompt"):
		doc.request_title = build_request_title(doc.prompt)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return doc.as_dict()


def _preview_data(doc):
	try:
		return json.loads(doc.raw_state or doc.preview or "{}")
	except Exception:
		return {}


def compact_preview(data):
	if not data:
		return {}
	if data.get("status") == "failed":
		return {
			"status": "failed",
			"error": data.get("error"),
			"error_type": data.get("error_type"),
		}
	interview = data.get("design_interview") or {}
	if interview and interview.get("status") == "waiting_for_answer":
		return {
			"stage": "design_interview",
			"status": "waiting_for_answer",
			"scope_type": interview.get("scope_type"),
			"domain": interview.get("domain"),
			"likely_action_count_range": interview.get("likely_action_count_range"),
			"active_question": interview.get("active_question"),
			"answered_count": interview.get("answered_count"),
			"remaining_count": interview.get("remaining_count"),
			"system_assumptions": interview.get("system_assumptions") or [],
		}
	if interview and interview.get("status") == "complete" and not any(
		data.get(key) for key in ("orchestration", "security_preparation", "approval_result", "sync_report")
	):
		return {
			"stage": "design_interview",
			"status": "complete",
			"scope_type": interview.get("scope_type"),
			"domain": interview.get("domain"),
			"likely_action_count_range": interview.get("likely_action_count_range"),
			"answered_count": len(interview.get("answers") or []),
			"system_assumptions": interview.get("system_assumptions") or [],
		}
	orchestration = data.get("orchestration") or {}
	security = data.get("security_preparation") or orchestration.get("security_preparation") or {}
	approval = data.get("approval_result") or {}
	sync = data.get("sync_report") or {}
	if sync:
		return compact_sync_result(approval, sync)
	if approval:
		return {
			"stage": "approval",
			"status": approval.get("status"),
			"approved_groups": approval.get("approved_group_ids") or [],
			"rejected_groups": approval.get("rejected_group_ids") or [],
			"waiting_operations": approval.get("waiting_operation_ids") or [],
			"blocked_operations": approval.get("blocked_operation_ids") or [],
			"invalid_reasons": approval.get("invalid_approval_reasons") or [],
		}
	if security:
		return compact_security(
			security,
			force_manual_approval=data.get("force_manual_approval"),
			approval_decisions=data.get("approval_decisions") or [],
		)
	if orchestration.get("results"):
		return {
			"stage": orchestration.get("stage"),
			"status": orchestration.get("status"),
			"answers": [
				{
					"answer": result.get("answer"),
					"confidence": result.get("confidence"),
					"facts": [fact.get("fact") for fact in result.get("facts") or []],
					"missing_information": result.get("missing_information") or [],
				}
				for result in orchestration.get("results") or []
			],
		}
	if orchestration.get("questions"):
		return {
			"stage": orchestration.get("stage"),
			"status": orchestration.get("status"),
			"questions": orchestration.get("questions"),
		}
	if orchestration:
		return {
			"stage": orchestration.get("stage"),
			"status": orchestration.get("status"),
			"plan_id": orchestration.get("plan_id"),
			"operation_count": orchestration.get("operation_count"),
		}
	return data


def compact_security(security, force_manual_approval=False, approval_decisions=None):
	if security.get("status") == "blocked" or security.get("blocked_reasons"):
		return {
			"stage": "security",
			"status": "blocked",
			"overall_risk_level": security.get("overall_risk_level"),
			"overall_risk_score": security.get("overall_risk_score"),
			"approval_required": False,
			"approval_prompts": [],
			"blocked_reasons": security.get("blocked_reasons") or ["Security review blocked execution."],
		}

	decided_group_ids = {
		decision.get("group_id") for decision in approval_decisions or []
	}
	required_prompts = [
		prompt for prompt in security.get("approval_prompts") or []
		if approval_required_for_prompt(prompt, force_manual_approval=force_manual_approval)
	]
	pending_prompts = [
		prompt for prompt in required_prompts
		if prompt.get("group_id") not in decided_group_ids
	]
	return {
		"stage": "security",
		"status": security.get("status"),
		"force_manual_approval": bool(force_manual_approval),
		"overall_risk_level": security.get("overall_risk_level"),
		"overall_risk_score": security.get("overall_risk_score"),
		"approval_required": bool(pending_prompts),
		"all_required_recorded": bool(required_prompts) and not pending_prompts,
		"auto_approved_low_risk_groups": [
			prompt.get("group_id") for prompt in security.get("approval_prompts") or []
			if not approval_required_for_prompt(prompt, force_manual_approval=force_manual_approval)
		],
		"approved_or_denied_group_ids": sorted(decided_group_ids),
		"approval_prompts": [
			{
				"group_id": prompt.get("group_id"),
				"title": prompt.get("title"),
				"risk_level": prompt.get("risk_level"),
				"risk_score": prompt.get("risk_score"),
				"operation_ids": prompt.get("operation_ids") or [],
				"prompt": prompt.get("prompt"),
			}
			for prompt in pending_prompts[:1]
		],
		"blocked_reasons": security.get("blocked_reasons") or [],
	}


def compact_sync_result(approval, sync):
	return {
		"stage": "sync",
		"approval_status": approval.get("status"),
		"sync_status": sync.get("status"),
		"message": sync.get("message"),
		"executed_operations": sync.get("executed_operation_ids") or [],
		"skipped_operations": sync.get("skipped_operation_ids") or [],
		"failed_operations": sync.get("failed_operation_ids") or [],
		"records": [
			{
				"operation_id": result.get("operation_id"),
				"operation_type": result.get("operation_type"),
				"status": result.get("status"),
				"message": result.get("message"),
				"record": result.get("record"),
				"before": summarize_record_for_console(result.get("before")),
				"after": summarize_record_for_console(result.get("after")),
			}
			for result in sync.get("results") or []
		],
	}


def summarize_record_for_console(record):
	if not record:
		return None
	return {
		key: record.get(key)
		for key in ("doctype", "name", "action_name", "status", "start_date", "end_date", "todo", "event")
		if key in record
	}


def _current_security(doc):
	data = _preview_data(doc)
	return data.get("security_preparation") or data.get("orchestration", {}).get("security_preparation")


def _current_plan(doc):
	data = _preview_data(doc)
	orchestration = data.get("orchestration") or {}
	plan = orchestration.get("execution_plan") or data.get("execution_plan")
	if not plan and orchestration.get("operations"):
		plan = _plan_from_orchestration_summary(orchestration)
	return plan


def _approval_decisions(doc):
	try:
		return json.loads(doc.approval_decisions or "[]")
	except Exception:
		return []


def _current_security_group_ids(security):
	return {
		prompt.get("group_id")
		for prompt in (security or {}).get("approval_prompts") or []
		if prompt.get("group_id")
	}


def _current_approval_decisions(doc, security=None):
	security = security or _current_security(doc) or {}
	valid_group_ids = _current_security_group_ids(security)
	if not valid_group_ids:
		return []
	return [
		decision for decision in _approval_decisions(doc)
		if decision.get("group_id") in valid_group_ids
	]


def _set_approval_decision(doc, group_id, approved):
	decisions = [decision for decision in _approval_decisions(doc) if decision.get("group_id") != group_id]
	security = _current_security(doc) or {}
	decisions.append({
		"group_id": group_id,
		"approved": bool(approved),
		"confirmation_phrase": _approval_phrase_for_group(security, group_id),
		"note": None if approved else "Denied from AI Execution Console",
	})
	doc.approval_decisions = _json(decisions)
	return decisions


def approval_required_for_security(security, force_manual_approval=False):
	if not security:
		return False
	if security.get("status") == "blocked":
		return False
	for prompt in security.get("approval_prompts") or []:
		if approval_required_for_prompt(prompt, force_manual_approval=force_manual_approval):
			return True
	return False


def approval_required_for_prompt(prompt, force_manual_approval=False):
	if force_manual_approval:
		return True
	return (
		prompt.get("explicit_confirmation_required")
		or prompt.get("risk_level") in {"high", "critical"}
		or float(prompt.get("risk_score") or 0) >= 0.7
	)


def decisions_for_auto_approved_security(security, force_manual_approval=False):
	return [
		ExecutionApprovalDecision(
			group_id=prompt.get("group_id"),
			approved=True,
			confirmation_phrase=prompt.get("confirmation_phrase"),
		)
		for prompt in security.get("approval_prompts") or []
		if not approval_required_for_prompt(prompt, force_manual_approval=force_manual_approval)
	]


def required_approval_group_ids(security, force_manual_approval=False):
	return {
		prompt.get("group_id")
		for prompt in security.get("approval_prompts") or []
		if approval_required_for_prompt(prompt, force_manual_approval=force_manual_approval)
	}


def all_required_approval_decisions_recorded(doc):
	security = _current_security(doc) or {}
	required = required_approval_group_ids(security, force_manual_approval=_force_manual_approval(doc))
	decided = {decision.get("group_id") for decision in _current_approval_decisions(doc, security)}
	return required.issubset(decided)


def pending_required_approval_prompts(data):
	security = data.get("security_preparation") or data.get("orchestration", {}).get("security_preparation") or {}
	decided = {
		decision.get("group_id") for decision in data.get("approval_decisions") or []
	}
	return [
		prompt for prompt in security.get("approval_prompts") or []
		if approval_required_for_prompt(
			prompt,
			force_manual_approval=data.get("force_manual_approval"),
		) and prompt.get("group_id") not in decided
	]


def prompt_requests_manual_approval(prompt):
	lower = (prompt or "").lower()
	approval_terms = (
		"ask permission",
		"ask for permission",
		"ask approval",
		"ask for approval",
		"permission for both",
		"approve both",
		"accept one and reject",
		"reject the other",
	)
	return any(term in lower for term in approval_terms)


def _force_manual_approval(doc):
	return prompt_requests_manual_approval(doc.prompt)


def _reset_run_state(doc):
	doc.stage = None
	doc.orchestration_id = None
	doc.plan_id = None
	doc.response = None
	doc.active_question_id = None
	doc.question_plan = None
	doc.question_answers = None
	doc.approval_group_id = None
	doc.approval_decision = None
	doc.approval_decisions = None


def _question_plan(doc):
	try:
		return json.loads(doc.question_plan or "null")
	except Exception:
		return None


def _question_answers(doc):
	try:
		return json.loads(doc.question_answers or "[]")
	except Exception:
		return []


def _set_question_plan(doc, plan):
	doc.question_plan = _json(plan.model_dump() if hasattr(plan, "model_dump") else plan)
	doc.active_question_id = (next_design_question(plan) or {}).question_id if next_design_question(plan) else None


def _set_question_answers(doc, answers):
	doc.question_answers = _json(answers)


def _active_design_question(doc):
	plan = _question_plan(doc)
	if not plan:
		return None
	question = next_design_question(plan)
	return question.model_dump() if question else None


def _start_progressive_design_interview(doc):
	plan = build_progressive_design_question_plan(doc.prompt, [])
	if not plan:
		return False
	_set_question_plan(doc, plan)
	_set_question_answers(doc, [])
	if not next_design_question(plan):
		return _finish_progressive_design_interview(doc)
	doc.status = "Waiting for User"
	doc.stage = "clarification"
	_set_preview(doc, {
		"design_interview": {
			"status": "waiting_for_answer",
			"scope_type": plan.scope_type,
			"domain": plan.domain,
			"likely_action_count_range": list(plan.likely_action_count_range),
			"active_question": _active_design_question(doc),
			"answered_count": 0,
			"remaining_count": len(plan.questions),
			"inferred_answers": plan.inferred_answers,
			"system_assumptions": plan.system_assumptions,
		}
	})
	return True


def _continue_progressive_design_interview(doc):
	if not _prompt_still_needs_design_interview(doc):
		doc.active_question_id = None
		doc.question_plan = None
		doc.question_answers = None
		doc.response = None
		return _run_initial_execution_pipeline(doc)
	plan = _question_plan(doc)
	if not plan:
		return False
	active_question = _active_design_question(doc)
	if not active_question:
		return _finish_progressive_design_interview(doc)
	if not doc.response:
		frappe.throw("Enter the answer in Response, then press Process again.")
	answers = _question_answers(doc)
	answers.append({
		"question_id": active_question.get("question_id"),
		"phase": active_question.get("phase"),
		"question": active_question.get("question"),
		"answer": doc.response,
	})
	new_plan = build_progressive_design_question_plan(doc.prompt, answers)
	_set_question_answers(doc, answers)
	doc.response = None
	if new_plan and next_design_question(new_plan):
		_set_question_plan(doc, new_plan)
		doc.status = "Waiting for User"
		doc.stage = "clarification"
		_set_preview(doc, {
			"design_interview": {
				"status": "waiting_for_answer",
				"scope_type": new_plan.scope_type,
				"domain": new_plan.domain,
				"likely_action_count_range": list(new_plan.likely_action_count_range),
				"active_question": _active_design_question(doc),
				"answered_count": len(answers),
				"remaining_count": len(new_plan.questions),
				"answers": answers,
				"inferred_answers": new_plan.inferred_answers,
				"system_assumptions": new_plan.system_assumptions,
			}
		})
		return _save(doc)
	_set_question_plan(doc, new_plan or plan)
	return _finish_progressive_design_interview(doc)


def _prompt_still_needs_design_interview(doc):
	answers = _question_answers(doc)
	scope = classify_design_scope(doc.prompt, answers)
	return scope.get("scope_type") != "simple_action"


def _run_initial_execution_pipeline(doc):
	result = preview_execution_security(doc.prompt)
	orchestration = result.get("orchestration") or {}
	doc.stage = orchestration.get("stage")
	doc.orchestration_id = orchestration.get("orchestration_id")
	doc.plan_id = orchestration.get("plan_id")
	if orchestration.get("execution_plan"):
		remember_execution_plan(ExecutionPlan.model_validate(orchestration.get("execution_plan")))
	security = result.get("security_preparation")
	if security:
		result["force_manual_approval"] = _force_manual_approval(doc)
	_set_preview(doc, result)
	if orchestration.get("status") == "needs_user":
		doc.status = "Waiting for User"
	elif orchestration.get("status") == "paused":
		doc.status = "Paused"
	elif security:
		if security.get("status") == "waiting_for_approval":
			doc.status = "Waiting for Approval" if approval_required_for_security(security, force_manual_approval=_force_manual_approval(doc)) else "Ready to Execute"
		elif security.get("status") == "blocked":
			doc.status = "Blocked"
		else:
			doc.status = "Ready to Execute"
	elif orchestration.get("status") == "answered":
		doc.status = "Executed"
		doc.stage = "complete"
	elif orchestration.get("plan_id"):
		doc.status = "Ready to Execute"
	if doc.status == "Ready to Execute":
		_save(doc)
		return execute_when_ready(doc)
	return _save(doc)


def _finish_progressive_design_interview(doc):
	plan = _question_plan(doc)
	answers = _combined_design_answers(plan, _question_answers(doc))
	brief = compile_design_brief(doc.prompt, plan, answers)
	doc.active_question_id = None
	doc.question_plan = None
	result = preview_execution_security(brief["clarified_prompt"])
	data = {
		"design_interview": {
			"status": "complete",
			"scope_type": brief["design_type"],
			"domain": brief["domain"],
			"likely_action_count_range": brief["likely_action_count_range"],
			"answers": answers,
			"system_assumptions": brief["system_assumptions"],
		},
		**result,
	}
	orchestration = result.get("orchestration") or {}
	doc.stage = orchestration.get("stage")
	doc.orchestration_id = orchestration.get("orchestration_id")
	doc.plan_id = orchestration.get("plan_id")
	if orchestration.get("execution_plan"):
		remember_execution_plan(ExecutionPlan.model_validate(orchestration.get("execution_plan")))
	security = result.get("security_preparation")
	if security:
		data["force_manual_approval"] = _force_manual_approval(doc)
	_set_preview(doc, data)
	if orchestration.get("status") == "needs_user":
		doc.status = "Waiting for User"
	elif security:
		doc.status = "Waiting for Approval" if approval_required_for_security(security, force_manual_approval=_force_manual_approval(doc)) else "Ready to Execute"
	elif orchestration.get("status") == "answered":
		doc.status = "Executed"
		doc.stage = "complete"
	elif orchestration.get("plan_id"):
		doc.status = "Ready to Execute"
	else:
		doc.status = "Paused" if orchestration.get("status") == "paused" else "Draft"
	if doc.status == "Ready to Execute":
		_save(doc)
		return execute_when_ready(doc)
	return _save(doc)


def _combined_design_answers(plan, answers):
	plan = plan or {}
	merged = list(answers or [])
	seen = {answer.get("question_id") for answer in merged}
	for answer in plan.get("inferred_answers") or []:
		if answer.get("question_id") not in seen:
			merged.append(answer)
			seen.add(answer.get("question_id"))
	return merged


def _plan_from_orchestration_summary(summary):
	return {
		"status": "ready",
		"plan_id": summary.get("plan_id"),
		"problem": {"goal": summary.get("input") or "AI Execution Console request"},
		"routes_considered": [{
			"route_id": (summary.get("route_selection") or {}).get("chosen_route_id") or summary.get("chosen_route_id") or "stored_route",
			"outcome_type": (summary.get("route_selection") or {}).get("outcome_type") or "plan",
			"description": "Route recovered from the console preview.",
			"expected_outcome": "Run the operations stored in the console preview.",
			"evidence": [{"source": "system", "reference": "AI Execution Console preview", "fact": "Recovered from stored preview JSON."}],
			"missing_information": [],
			"risks": (summary.get("route_selection") or {}).get("risks") or [],
			"system_objects": (summary.get("route_selection") or {}).get("system_objects") or [],
			"reversibility": "medium",
			"confidence": (summary.get("route_selection") or {}).get("confidence") or 1,
			"score": (summary.get("route_selection") or {}).get("score") or 1,
		}],
		"chosen_route_id": (summary.get("route_selection") or {}).get("chosen_route_id") or summary.get("chosen_route_id") or "stored_route",
		"decisions": [{
			"decision_id": operation.get("decision_id") or f"decision_{index + 1}",
			"question": "Recovered implementation decision",
			"conclusion": operation.get("description") or operation.get("operation_id"),
			"alternatives": [],
			"confidence": 1,
			"evidence": [{"source": "system", "reference": "AI Execution Console preview", "fact": "Recovered from stored preview JSON."}],
		} for index, operation in enumerate(summary.get("operations") or [])],
		"operations": summary.get("operations") or [],
		"success_criteria": summary.get("success_criteria") or [{
			"description": "Operations complete",
			"check": "Inspect execution report.",
			"expected_result": "All approved operations complete or report a clear failure.",
		}],
	}


def build_readable_output(data):
	if not data:
		return None
	if data.get("status") == "failed":
		return f"Failed: {data.get('error')}"
	interview = data.get("design_interview") or {}
	if interview and interview.get("status") == "waiting_for_answer":
		question = interview.get("active_question") or {}
		lines = [
			f"Design scope: {interview.get('scope_type')} / {interview.get('domain')}",
			f"Estimated size: {interview.get('likely_action_count_range')}",
			f"Question: {question.get('question')}",
			f"Why: {question.get('reason')}",
		]
		if question.get("options"):
			lines.append("Options: " + ", ".join(question.get("options")))
		if question.get("default_assumption"):
			lines.append(f"Default assumption if you agree: {question.get('default_assumption')}")
		return "\n".join(line for line in lines if line)
	if interview and interview.get("status") == "complete":
		return (
			f"Design interview complete: {interview.get('scope_type')} / {interview.get('domain')}\n"
			f"Estimated size: {interview.get('likely_action_count_range')}\n"
			"Continuing to route, implementation, security, and sync."
		)
	orchestration = data.get("orchestration") or {}
	if orchestration.get("results"):
		return build_information_readable_output(orchestration.get("results") or [])
	questions = orchestration.get("questions") or []
	if questions:
		return "\n".join(
			f"Question {index + 1}: {question.get('question')}\nWhy: {question.get('reason')}"
			for index, question in enumerate(questions)
		)
	security = data.get("security_preparation") or orchestration.get("security_preparation") or {}
	if security.get("status") == "blocked" or security.get("blocked_reasons"):
		return "Blocked:\n" + "\n".join(
			f"- {reason}" for reason in security.get("blocked_reasons") or ["Security review blocked execution."]
		)
	approval_status = data.get("approval_status") or {}
	if approval_status.get("all_required_recorded"):
		return approval_status.get("message") or "All required permissions are recorded. Press Process to continue execution."
	prompts = pending_required_approval_prompts(data)
	if prompts:
		return "\n\n".join(
			f"Permission {index + 1}: {prompt.get('title')}\nRisk: {prompt.get('risk_level')} ({prompt.get('risk_score')})\n{prompt.get('prompt')}"
			for index, prompt in enumerate(prompts[:1])
		)
	if data.get("force_manual_approval") and security.get("approval_prompts"):
		return "All required permissions are recorded. Press Process to sync approved operations."
	if security.get("approval_prompts"):
		return "Low-risk operation approved automatically; execution is continuing."
	approval = data.get("approval_result") or {}
	sync = data.get("sync_report") or {}
	if sync:
		return build_sync_readable_output(sync)
	if approval:
		return f"Approval status: {approval.get('status')}"
	if orchestration:
		return f"Orchestration status: {orchestration.get('status')} at stage {orchestration.get('stage')}"
	return None


def build_sync_readable_output(sync):
	lines = [f"Sync status: {sync.get('status')}", sync.get("message") or ""]
	for result in sync.get("results") or []:
		line = f"- {result.get('operation_id')}: {result.get('message')}"
		after = summarize_record_for_console(result.get("after"))
		before = summarize_record_for_console(result.get("before"))
		if after:
			line += f" | after={after}"
		elif before:
			line += f" | before={before}"
		lines.append(line)
	return "\n".join(line for line in lines if line)


def build_information_readable_output(results):
	lines = []
	for index, result in enumerate(results, start=1):
		lines.append(f"Result {index}: {result.get('answer')}")
		for fact in result.get("facts") or []:
			lines.append(f"- {fact.get('fact')}")
		for missing in result.get("missing_information") or []:
			lines.append(f"Missing: {missing}")
	return "\n".join(lines)


def _restore_execution_cache_from_console(doc):
	if not doc.plan_id:
		return
	plan = _current_plan(doc)
	if plan:
		remember_execution_plan(ExecutionPlan.model_validate(plan))
	security = _current_security(doc)
	if security:
		remember_execution_preparation(ExecutionPreparation.model_validate({
			"plan_id": doc.plan_id,
			"status": security.get("status"),
			"security_review": security,
		}))


def _apply_stored_approval_decisions(doc):
	_restore_execution_cache_from_console(doc)
	preparation = get_cached_execution_preparation(doc.plan_id)
	security = _current_security(doc) or {}
	manual_decisions = [ExecutionApprovalDecision.model_validate(decision) for decision in _current_approval_decisions(doc, security)]
	auto_decisions = decisions_for_auto_approved_security(security, force_manual_approval=_force_manual_approval(doc))
	manual_group_ids = {decision.group_id for decision in manual_decisions}
	decisions = manual_decisions + [decision for decision in auto_decisions if decision.group_id not in manual_group_ids]
	return apply_execution_approvals(preparation, decisions)


def execute_when_ready(doc):
	approval = _apply_stored_approval_decisions(doc)
	approval_result = summarize_execution_approval_result(approval)
	if approval_result.get("status") in {"waiting_for_approval", "blocked", "rejected"}:
		data = _preview_data(doc)
		data["approval_result"] = approval_result
		data["security_preparation"] = _current_security(doc)
		_set_preview(doc, data)
		doc.status = "Waiting for Approval" if approval_result.get("status") == "waiting_for_approval" else "Blocked"
		doc.response = None
		doc.approval_group_id = None
		doc.approval_decision = None
		return _save(doc)

	plan = get_cached_execution_plan(doc.plan_id)
	report = sync_approved_execution(plan, approval)
	result = {
		"approval_result": approval_result,
		"sync_report": summarize_execution_sync_report(report),
	}
	doc.status = "Executed" if result["sync_report"].get("status") == "complete" else "Blocked"
	doc.stage = "complete"
	_set_preview(doc, result)
	doc.response = None
	doc.approval_group_id = None
	doc.approval_decision = None
	doc.approval_decisions = None
	return _save(doc)


def _publish_console_update(doc):
	frappe.publish_realtime(
		"ai_execution_console_update",
		{
			"name": doc.name,
			"status": doc.status,
			"stage": doc.stage,
		},
		doctype="AI Execution Console",
		docname=doc.name,
		after_commit=True,
	)


def _fail(doc, error):
	doc.status = "Failed"
	error_message = str(error) or repr(error) or error.__class__.__name__
	_set_preview(doc, {
		"status": "failed",
		"error": error_message,
		"error_type": error.__class__.__name__,
		"traceback_tail": traceback.format_exc().splitlines()[-8:],
	})
	_save(doc)


def _apply_orchestration(doc, result):
	summary = summarize_orchestration_result(result)
	doc.stage = summary.get("stage")
	doc.orchestration_id = summary.get("orchestration_id")
	doc.plan_id = summary.get("plan_id")
	_set_preview(doc, {"orchestration": summary})
	if isinstance(result.output, ExecutionPlan):
		remember_execution_plan(result.output)

	if summary.get("status") == "needs_user":
		doc.status = "Waiting for User"
	elif summary.get("status") == "paused":
		doc.status = "Paused"
	elif summary.get("stage") == "execution" and summary.get("plan_id"):
		doc.status = "Ready to Execute"
	else:
		doc.status = "Draft"

	return summary


def _apply_security(doc, security):
	data = _preview_data(doc)
	data["security_preparation"] = security
	data["force_manual_approval"] = _force_manual_approval(doc)
	_set_preview(doc, data)
	if security.get("status") == "waiting_for_approval":
		doc.status = "Waiting for Approval" if approval_required_for_security(security, force_manual_approval=_force_manual_approval(doc)) else "Ready to Execute"
	elif security.get("status") == "blocked":
		doc.status = "Blocked"
	elif security.get("status") == "ready_to_execute":
		doc.status = "Ready to Execute"


def _prepare_response_for_approval(doc):
	response = (doc.response or "").strip()
	if not response:
		return None
	if response.lower() in {"reject", "rejected", "no", "deny"}:
		return "reject"
	return response


def _preview_approval_status(plan_id, confirmation_phrase):
	preparation = get_cached_execution_preparation(plan_id)
	decisions = [
		ExecutionApprovalDecision(
			group_id=prompt.group_id,
			approved=True,
			confirmation_phrase=confirmation_phrase,
		)
		for prompt in preparation.security_review.approval_prompts
	]
	return summarize_execution_approval_result(apply_execution_approvals(preparation, decisions))


def _decision_from_label(label):
	return str(label or "").strip().lower() in {"approve", "approved", "yes", "true", "1"}


def _approval_phrase_for_group(security, group_id):
	for prompt in security.get("approval_prompts") or []:
		if prompt.get("group_id") == group_id:
			return prompt.get("confirmation_phrase")
	return None


@frappe.whitelist()
def process(name):
	doc = frappe.get_doc("AI Execution Console", name)
	if doc.status == "Processing":
		return doc.as_dict()
	if _question_plan(doc) and not _prompt_still_needs_design_interview(doc):
		doc.active_question_id = None
		doc.question_plan = None
		doc.question_answers = None
		doc.response = None
	previous_status = doc.status or "Draft"
	doc.status = "Queued"
	_save(doc)
	_publish_console_update(doc)
	frappe.enqueue(
		"kratium.execution_system.doctype.ai_execution_console.ai_execution_console.process_background",
		queue="long",
		job_name=f"AI Execution Console {name}",
		name=name,
		previous_status=previous_status,
	)
	return doc.as_dict()


@frappe.whitelist()
def recover_stale_interview(name):
	doc = frappe.get_doc("AI Execution Console", name)
	if _question_plan(doc) and not _prompt_still_needs_design_interview(doc):
		doc.active_question_id = None
		doc.question_plan = None
		doc.question_answers = None
		doc.response = None
		return _run_initial_execution_pipeline(doc)
	return doc.as_dict()


def process_background(name, previous_status="Draft"):
	doc = frappe.get_doc("AI Execution Console", name)
	doc.status = "Processing"
	_save(doc)
	_publish_console_update(doc)
	try:
		if previous_status == "Ready to Execute":
			return execute_when_ready(doc)

		if previous_status in {None, "", "Draft", "Queued", "Paused", "Failed"}:
			if previous_status == "Failed" and doc.plan_id and _current_security(doc):
				return execute_when_ready(doc)
			_reset_run_state(doc)
			if _start_progressive_design_interview(doc):
				return _save(doc)
			return _run_initial_execution_pipeline(doc)

		if previous_status == "Waiting for User":
			if _question_plan(doc):
				return _continue_progressive_design_interview(doc)
			if not doc.response:
				frappe.throw("Enter the answer in Response, then press Process again.")
			result = continue_cached_orchestration(doc.orchestration_id, doc.response)
			_apply_orchestration(doc, result)
			if isinstance(result.output, ExecutionPlan):
				remember_execution_plan(result.output)
				security = preview_execution_security_for_plan(result.output)
				_apply_security(doc, security)
			doc.response = None
			if doc.status == "Ready to Execute":
				_save(doc)
				return execute_when_ready(doc)
			return _save(doc)

		if previous_status == "Waiting for Approval":
			if not all_required_approval_decisions_recorded(doc):
				_set_preview(doc, {
					"status": "waiting_for_approval",
					"message": "Use the approval buttons for each permission request before processing.",
					"security_preparation": _current_security(doc),
					"approval_decisions": _current_approval_decisions(doc),
					"force_manual_approval": _force_manual_approval(doc),
				})
				doc.status = "Waiting for Approval"
				return _save(doc)
			return execute_when_ready(doc)

		frappe.throw(f"No process action is available for status {previous_status}.")
	except Exception as error:
		_fail(doc, error)
		raise


@frappe.whitelist()
def create_test_console(prompt=None):
	prompt = prompt or (
		"Create a calendar event called AI console test exercise on 2026-07-06 from 09:00 to 10:00. "
		"Also check what I have planned after 21:00 on 2026-07-06. "
		"If there is nothing after 21:00, create a temporary event called AI console temporary delete test "
		"from 21:30 to 22:00 and then delete it."
	)
	doc = frappe.get_doc({
		"doctype": "AI Execution Console",
		"prompt": prompt,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name


@frappe.whitelist()
def create_sample_approval_console():
	plan = remember_execution_plan(build_sample_create_plan(1))
	security = summarize_execution_preparation(remember_execution_preparation(prepare_execution(plan)))
	doc = frappe.get_doc({
		"doctype": "AI Execution Console",
		"prompt": "Deterministic sample approval console test",
		"status": "Waiting for Approval",
		"stage": "execution",
		"plan_id": plan.plan_id,
	})
	_set_preview(doc, {
		"orchestration": {
			"stage": "execution",
			"status": "ready",
			"plan_id": plan.plan_id,
			"execution_plan": plan.model_dump(),
		},
		"security_preparation": security,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name


@frappe.whitelist()
def preview_design_interview(prompt, answers_json=None):
	answers = json.loads(answers_json or "[]")
	plan = build_progressive_design_question_plan(prompt, answers)
	if not plan:
		return {"status": "not_required"}
	question = next_design_question(plan)
	combined_answers = _combined_design_answers(plan.model_dump(), answers)
	return {
		"status": "waiting_for_answer" if question else "complete",
		"scope_type": plan.scope_type,
		"domain": plan.domain,
		"likely_action_count_range": list(plan.likely_action_count_range),
		"active_question": question.model_dump() if question else None,
		"answered_count": len(combined_answers),
		"remaining_count": len(plan.questions),
		"inferred_answers": plan.inferred_answers,
		"system_assumptions": plan.system_assumptions,
		"answers": combined_answers,
		"design_brief": compile_design_brief(prompt, plan, combined_answers) if not question else None,
	}


@frappe.whitelist()
def approve_group(name, group_id, decision):
	doc = frappe.get_doc("AI Execution Console", name)
	if doc.status != "Waiting for Approval":
		frappe.throw("This request is not waiting for approval.")
	doc.approval_group_id = group_id
	doc.approval_decision = "Approve" if _decision_from_label(decision) else "Deny"
	_set_approval_decision(doc, group_id, _decision_from_label(decision))
	data = _preview_data(doc)
	data["security_preparation"] = _current_security(doc)
	data["force_manual_approval"] = _force_manual_approval(doc)
	data["approval_decisions"] = _current_approval_decisions(doc)
	all_recorded = all_required_approval_decisions_recorded(doc)
	data["approval_status"] = {
		"all_required_recorded": all_recorded,
		"message": (
			"All required permissions are recorded. Press Process to sync approved operations."
			if all_recorded
			else "Permission recorded. Continue approving the remaining permission requests."
		),
	}
	doc.approval_decisions = _json(data["approval_decisions"])
	_set_preview(doc, data)
	doc.status = "Ready to Execute" if all_recorded else "Waiting for Approval"
	return _save(doc)


@frappe.whitelist()
def recompute_security_from_raw_state(name):
	doc = frappe.get_doc("AI Execution Console", name)
	plan = _current_plan(doc)
	if not plan:
		frappe.throw("No execution plan is stored on this console request.")
	plan = remember_execution_plan(ExecutionPlan.model_validate(plan))
	security = preview_execution_security_for_plan(plan)
	data = _preview_data(doc)
	data["security_preparation"] = security
	data["force_manual_approval"] = _force_manual_approval(doc)
	_set_preview(doc, data)
	doc.status = "Waiting for Approval" if approval_required_for_security(security, force_manual_approval=_force_manual_approval(doc)) else "Ready to Execute"
	if security.get("status") == "blocked":
		doc.status = "Blocked"
	elif doc.status == "Ready to Execute":
		_save(doc)
		return execute_when_ready(doc)
	return _save(doc)


@frappe.whitelist()
def backfill_request_titles():
	updated = 0
	for name, prompt in frappe.get_all(
		"AI Execution Console",
		fields=["name", "prompt"],
		filters=[["request_title", "in", ["", None]]],
		as_list=True,
	):
		frappe.db.set_value(
			"AI Execution Console",
			name,
			"request_title",
			build_request_title(prompt),
			update_modified=False,
		)
		updated += 1
	frappe.db.commit()
	return {"updated": updated}
