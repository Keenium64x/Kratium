frappe.ui.form.on("AI Execution Console", {
	refresh(frm) {
		frm.clear_custom_buttons();
		frm.page?.clear_inner_toolbar?.();
		frm.toggle_reqd("response", frm.doc.status === "Waiting for User");
		frm.toggle_display("response", frm.doc.status === "Waiting for User");
		frm.set_df_property("prompt", "read_only", frm.doc.status && frm.doc.status !== "Draft");

		render_readable_state(frm);

		if (["Queued", "Processing"].includes(frm.doc.status)) {
			frm.dashboard.set_headline_alert(
				`<span class="indicator blue">${frm.doc.status}: AI job running in background ⏳</span>`,
				"blue"
			);
			frm.disable_save();
			setTimeout(() => frm.reload_doc(), 3000);
			return;
		}

		if (!frm.is_new()) {
			frm.enable_save();
		}

		set_status_headline(frm);
		add_process_button(frm);
		add_approval_buttons(frm);
	},

	onload(frm) {
		frappe.realtime.on("ai_execution_console_update", (data) => {
			if (data.name === frm.doc.name) {
				frm.reload_doc();
			}
		});
	},
});

function add_process_button(frm) {
	if (!should_show_process_button(frm)) return;

	frm.add_custom_button("Process", () => {
		if (frm.is_new()) {
			frappe.msgprint("Save this request before processing it.");
			return;
		}
		if (frm.is_dirty()) {
			frappe.msgprint("Save your changes before processing.");
			return;
		}
		frappe.call({
			method: "kratium.execution_system.doctype.ai_execution_console.ai_execution_console.process",
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: "Sending to background worker...",
			callback() {
				frm.reload_doc();
			},
		});
	});
}

function should_show_process_button(frm) {
	if (is_unsaved_doc(frm)) return false;
	if (["Queued", "Processing", "Executed"].includes(frm.doc.status)) return false;
	if (frm.doc.status === "Waiting for Approval") return all_required_approvals_recorded(frm);
	return ["Draft", "Paused", "Failed", "Waiting for User", "Ready to Execute"].includes(frm.doc.status || "Draft");
}

function is_unsaved_doc(frm) {
	return frm.is_new()
		|| frm.doc.__islocal
		|| frm.doc.__unsaved
		|| !frm.doc.name
		|| String(frm.doc.name || "").startsWith("new-");
}

function add_approval_buttons(frm) {
	if (frm.doc.status !== "Waiting for Approval") return;
	const decided = approval_decision_map(frm);
	const forceManualApproval = force_manual_approval(frm);
	const prompts = pending_required_prompts(frm);
	prompts.slice(0, 1).forEach((prompt, index) => {
		if (decided[prompt.group_id] !== undefined) return;
		const label = prompts.length > 1 ? `Approve Next` : "Approve";
		frm.add_custom_button(label, () => send_approval(frm, prompt.group_id, "Approve"), "Permissions");
		frm.add_custom_button(prompts.length > 1 ? "Deny Next" : "Deny", () => send_approval(frm, prompt.group_id, "Deny"), "Permissions");
	});
}

function send_approval(frm, group_id, decision) {
	frappe.call({
		method: "kratium.execution_system.doctype.ai_execution_console.ai_execution_console.approve_group",
		args: { name: frm.doc.name, group_id, decision },
		freeze: true,
		freeze_message: `${decision} permission...`,
		callback() {
			frm.reload_doc();
		},
	});
}

function render_readable_state(frm) {
	const data = parse_preview(frm);
	const interview = data?.design_interview || {};
	const questions = data?.orchestration?.questions || [];
	const security = get_security(frm);
	const prompts = pending_required_prompts(frm);

	if (interview.status === "waiting_for_answer") {
		const question = interview.active_question || {};
		let text = [
			`Design scope: ${interview.scope_type || "unknown"} / ${interview.domain || "unknown"}`,
			`Estimated size: ${JSON.stringify(interview.likely_action_count_range || [])}`,
			`Question: ${question.question || "Answer the current design question."}`,
			`Why: ${question.reason || "Needed to define the structure before implementation."}`,
		].join("\n");
		if ((question.options || []).length) {
			text += `\nOptions: ${question.options.join(", ")}`;
		}
		if (question.default_assumption) {
			text += `\nDefault assumption if you agree: ${question.default_assumption}`;
		}
		set_readable_output(frm, text);
		return;
	}

	if (questions.length) {
		const text = questions.map((question, index) => {
			return `Question ${index + 1}: ${question.question}\nWhy: ${question.reason || "Needed to continue safely."}`;
		}).join("\n\n");
		set_readable_output(frm, text);
		return;
	}

	if (security?.status === "blocked" || (security?.blocked_reasons || []).length) {
		const reasons = security.blocked_reasons?.length ? security.blocked_reasons : ["Security review blocked execution."];
		const text = `Blocked:\n${reasons.map((reason) => `- ${reason}`).join("\n")}`;
		set_readable_output(frm, text);
		return;
	}

	if (data?.approval_status?.all_required_recorded || (get_security_prompts(frm).length && all_required_approvals_recorded(frm))) {
		const text = data.approval_status.message || "All required permissions are recorded. Press Process to continue execution.";
		set_readable_output(frm, text);
		return;
	}

	if (prompts.length) {
		const text = prompts.slice(0, 1).map((prompt, index) => {
			return `Permission ${index + 1}: ${prompt.title}\nRisk: ${prompt.risk_level} (${prompt.risk_score})\n${prompt.prompt}`;
		}).join("\n\n");
		set_readable_output(frm, text);
	}
}

function set_readable_output(frm, text) {
	if (frm.doc.readable_output === text) return;
	frm.doc.readable_output = text;
	frm.refresh_field("readable_output");
}

function set_status_headline(frm) {
	if (!frm.doc.status) return;
	const colors = {
		Draft: "gray",
		"Waiting for User": "yellow",
		"Waiting for Approval": "orange",
		"Ready to Execute": "purple",
		Executed: "green",
		Paused: "gray",
		Blocked: "red",
		Failed: "red",
	};
	frm.dashboard.set_headline_alert(
		`<span class='indicator ${colors[frm.doc.status] || "gray"}'>${frm.doc.status}</span>`,
		colors[frm.doc.status] || "gray"
	);
}

function get_security_prompts(frm) {
	return get_security(frm)?.approval_prompts || [];
}

function pending_required_prompts(frm) {
	const forceManualApproval = force_manual_approval(frm);
	const decided = approval_decision_map(frm);
	return get_security_prompts(frm).filter((prompt) => {
		return approval_required_for_prompt(prompt, forceManualApproval)
			&& decided[prompt.group_id] === undefined;
	});
}

function get_security(frm) {
	const data = parse_preview(frm);
	return data?.security_preparation || data?.orchestration?.security_preparation || {};
}


function approval_required_for_prompt(prompt, forceManualApproval = false) {
	if (forceManualApproval) return true;
	return Boolean(prompt.explicit_confirmation_required)
		|| ["high", "critical"].includes(prompt.risk_level)
		|| Number(prompt.risk_score || 0) >= 0.7;
}

function all_required_approvals_recorded(frm) {
	const forceManualApproval = force_manual_approval(frm);
	const required = get_security_prompts(frm).filter((prompt) => approval_required_for_prompt(prompt, forceManualApproval)).map((prompt) => prompt.group_id);
	if (!required.length) return true;
	const decided = approval_decision_map(frm);
	return required.every((group_id) => decided[group_id] !== undefined);
}

function force_manual_approval(frm) {
	const data = parse_preview(frm);
	if (data?.force_manual_approval) return true;
	const prompt = String(frm.doc.prompt || "").toLowerCase();
	return [
		"ask permission",
		"ask for permission",
		"ask approval",
		"ask for approval",
		"permission for both",
		"approve both",
		"accept one and reject",
		"reject the other",
	].some((term) => prompt.includes(term));
}

function approval_decision_map(frm) {
	let decisions = [];
	try {
		decisions = JSON.parse(frm.doc.approval_decisions || "[]");
	} catch {
		decisions = [];
	}
	return Object.fromEntries(decisions.map((decision) => [decision.group_id, decision.approved]));
}

function parse_preview(frm) {
	try {
		return JSON.parse(frm.doc.raw_state || frm.doc.preview || "{}");
	} catch {
		return {};
	}
}
