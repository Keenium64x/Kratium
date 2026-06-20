from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

import frappe
from frappe.utils import get_datetime, now_datetime

from kratium.notifications import normalize_data


VALID_REMINDER_TYPES = {
	"Once",
	"Until Completion",
	"Before Completion",
	"Snooze",
	"Follow Up",
}
RECURRING_REMINDER_TYPES = {"Until Completion", "Follow Up"}


def schedule_reminder(
	user: str,
	title: str,
	body: str,
	run_at: Any,
	*,
	data: dict[str, Any] | str | None = None,
	route: str | None = None,
	reminder_type: str = "Once",
	repeat_every: Any = None,
	event_type: str = "reminder",
	action: str | None = None,
) -> str:
	if not user or not frappe.db.exists("User", user):
		raise ValueError("A valid reminder user is required")
	if not run_at:
		raise ValueError("A reminder time is required")

	reminder_type = reminder_type or "Once"
	if reminder_type not in VALID_REMINDER_TYPES:
		raise ValueError(f"Unsupported reminder type: {reminder_type}")

	run_at = get_datetime(run_at)
	interval = interval_seconds(repeat_every)
	if reminder_type in RECURRING_REMINDER_TYPES and interval <= 0:
		raise ValueError(f"{reminder_type} reminders require a positive repeat interval")

	doc = frappe.get_doc(
		{
			"doctype": "Reminder Master",
			"name1": str(title or "").strip() or "Kratium reminder",
			"description": str(body or "").strip(),
			"recipient": user,
			"remind_at": run_at,
			"reminder_type": reminder_type,
			"reminder_interval": interval or None,
			"reminder_for": action,
			"route": route,
			"event_type": event_type or "reminder",
			"data_json": json.dumps(normalize_data(data), separators=(",", ":")),
			"status": "Pending",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def schedule_reminder_in(
	user: str,
	title: str,
	body: str,
	*,
	seconds: float = 0,
	minutes: float = 0,
	hours: float = 0,
	days: float = 0,
	**kwargs: Any,
) -> str:
	run_at = now_datetime() + timedelta(
		seconds=float(seconds),
		minutes=float(minutes),
		hours=float(hours),
		days=float(days),
	)
	return schedule_reminder(user, title, body, run_at, **kwargs)


def reschedule_reminder(reminder_name: str, run_at: Any) -> str:
	doc = frappe.get_doc("Reminder Master", reminder_name)
	doc.remind_at = get_datetime(run_at)
	doc.status = "Pending"
	doc.attempt_count = 0
	doc.last_error = None
	doc.fired_at = None
	doc.save(ignore_permissions=True)
	return doc.name


def cancel_reminder(reminder_name: str) -> str:
	doc = frappe.get_doc("Reminder Master", reminder_name)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	return doc.name


def sync_action_reminder(action: Any) -> str | None:
	latest = frappe.db.get_value(
		"Reminder Master",
		{"reminder_for": action.name},
		["name", "status", "remind_at", "reminder_type"],
		as_dict=True,
		order_by="creation desc",
	)

	if not action.reminder or action.status == "Completed":
		if latest and latest.status in {"Pending", "Processing"}:
			frappe.db.set_value("Reminder Master", latest.name, "status", "Cancelled")
		return None

	reminder_type = action.reminder_type or "Once"
	interval = interval_seconds(action.reminder_interval)
	if reminder_type in RECURRING_REMINDER_TYPES and interval <= 0:
		frappe.throw(f"{reminder_type} reminders require a reminder interval")

	data = {
		"action": action.name,
		"reference_doctype": "Action",
		"reference_name": action.name,
	}
	values = {
		"name1": action.action_name or "Action reminder",
		"description": action.description or "",
		"recipient": action.owner,
		"remind_at": get_datetime(action.reminder),
		"reminder_type": reminder_type,
		"reminder_interval": interval or None,
		"route": f"/kratium/action/{action.name}",
		"event_type": "action_reminder",
		"data_json": json.dumps(data, separators=(",", ":")),
		"status": "Pending",
		"attempt_count": 0,
		"last_error": None,
	}

	if latest and latest.status in {"Pending", "Processing"}:
		if latest.status == "Pending":
			frappe.db.set_value("Reminder Master", latest.name, values)
		return latest.name

	if (
		latest
		and latest.status in {"Fired", "Failed"}
		and get_datetime(latest.remind_at) == values["remind_at"]
		and latest.reminder_type == reminder_type
	):
		return latest.name

	return schedule_reminder(
		action.owner,
		values["name1"],
		values["description"],
		values["remind_at"],
		data=data,
		route=values["route"],
		reminder_type=reminder_type,
		repeat_every=interval,
		event_type=values["event_type"],
		action=action.name,
	)


def interval_seconds(value: Any) -> float:
	if value in (None, ""):
		return 0
	if isinstance(value, timedelta):
		return value.total_seconds()
	if isinstance(value, (int, float)):
		return float(value)

	text = str(value).strip().lower()
	if not text:
		return 0
	try:
		return float(text)
	except ValueError:
		pass

	total = 0.0
	units = {
		"d": 86400,
		"day": 86400,
		"days": 86400,
		"h": 3600,
		"hour": 3600,
		"hours": 3600,
		"m": 60,
		"min": 60,
		"minute": 60,
		"minutes": 60,
		"s": 1,
		"sec": 1,
		"second": 1,
		"seconds": 1,
	}
	matches = re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", text)
	for amount, unit in matches:
		if unit not in units:
			raise ValueError(f"Unsupported reminder interval unit: {unit}")
		total += float(amount) * units[unit]

	if not matches:
		raise ValueError(f"Could not parse reminder interval: {value}")
	return total
