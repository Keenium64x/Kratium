from __future__ import annotations

import json
import time
from datetime import timedelta

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from kratium.notifications import Notification, NotificationDeliveryError, send_notification
from kratium.precision_scheduler import (
	ensure_precision_scheduler,
	queue_precise_delivery_after_commit,
	schedule_precise_delivery,
)
from kratium.reminders import RECURRING_REMINDER_TYPES, interval_seconds


MAX_DELIVERY_ATTEMPTS = 5
STALE_PROCESSING_MINUTES = 15
MAX_DELIVERY_LATENESS_SECONDS = 30
RETRY_DELAYS_MINUTES = (1, 5, 15, 30, 60)


def dispatch_reminders(limit: int = 200) -> dict[str, int]:
	"""Watchdog for reminders whose precise Redis job needs recovery."""
	recovered = recover_stale_reminders()
	ensure_precision_scheduler()
	due = frappe.get_all(
		"Reminder Master",
		filters={
			"status": "Pending",
			"remind_at": ["<=", now_datetime()],
		},
		fields=["name", "recipient", "owner", "remind_at"],
		order_by="remind_at asc",
		limit=limit,
	)

	requeued = 0
	missed = 0
	for row in due:
		lateness = (now_datetime() - get_datetime(row.remind_at)).total_seconds()
		if lateness > MAX_DELIVERY_LATENESS_SECONDS:
			_mark_missed_or_advance(row.name, f"Reminder was {round(lateness)} seconds late")
			missed += 1
			continue

		schedule_precise_delivery(
			row.name,
			now_datetime(),
			row.recipient or row.owner,
		)
		requeued += 1

	return {"requeued": requeued, "missed": missed, "recovered": recovered}


def deliver_reminder(reminder_name: str, claimed: bool = False) -> dict:
	if not claimed:
		row = frappe.db.get_value(
			"Reminder Master",
			reminder_name,
			["status", "remind_at"],
			as_dict=True,
		)
		if not row or row.status != "Pending":
			return {"status": row.status if row else "Missing", "skipped": True}
		seconds_until_due = (get_datetime(row.remind_at) - now_datetime()).total_seconds()
		if seconds_until_due < -MAX_DELIVERY_LATENESS_SECONDS:
			return _mark_missed_or_advance(
				reminder_name,
				f"Reminder was {round(abs(seconds_until_due))} seconds late",
			)
		if seconds_until_due > 1:
			return {"status": row.status, "skipped": True, "reason": "rescheduled"}
		if seconds_until_due > 0:
			# RQ stores delayed timestamps to whole-second precision. Waiting for
			# the remaining fraction prevents an early release without adding a
			# full extra second to every reminder.
			time.sleep(seconds_until_due)

		frappe.db.sql(
			"""
			UPDATE `tabReminder Master`
			SET status = 'Processing', modified = NOW()
			WHERE name = %s AND status = 'Pending'
			""",
			reminder_name,
		)
		if _affected_rows() != 1:
			return {"status": "Pending", "skipped": True, "reason": "already claimed"}

	doc = frappe.get_doc("Reminder Master", reminder_name, for_update=True)
	if doc.status != "Processing":
		return {"status": doc.status, "skipped": True}

	recipient = doc.recipient or doc.owner
	data = _load_data(doc.data_json)
	data.setdefault("reminder_id", doc.name)
	if doc.reminder_for:
		data.setdefault("action", doc.reminder_for)

	try:
		result = send_notification(
			Notification(
				user=recipient,
				title=doc.name1,
				body=doc.description,
				data=data,
				route=doc.route,
				event_type=doc.event_type or "reminder",
				notification_id=doc.name,
			),
			raise_on_total_failure=True,
		)
	except Exception as error:
		_retry_or_fail(doc, error)
		return {"status": doc.status, "error": str(error)}

	complete_delivery(doc, result)
	return {"status": doc.status, "delivery": result}


def complete_delivery(doc, result: dict | None = None) -> None:
	doc.attempt_count = 0
	doc.last_error = None
	doc.fired_at = now_datetime()
	doc.delivery_result = json.dumps(result or {}, indent=2, default=str)

	if _should_repeat(doc):
		doc.remind_at = _next_occurrence(doc.remind_at, doc.reminder_interval)
		doc.status = "Pending"
	else:
		doc.status = "Fired"

	doc.save(ignore_permissions=True)
	if doc.status == "Pending":
		queue_precise_delivery_after_commit(
			doc.name,
			get_datetime(doc.remind_at),
			doc.recipient or doc.owner,
		)


def recover_stale_reminders() -> int:
	stale_before = add_to_date(now_datetime(), minutes=-STALE_PROCESSING_MINUTES)
	frappe.db.sql(
		"""
		UPDATE `tabReminder Master`
		SET status = 'Pending',
			last_error = 'Recovered after an interrupted delivery worker',
			modified = NOW()
		WHERE status = 'Processing' AND modified <= %s
		""",
		stale_before,
	)
	return _affected_rows()


def reminder_scheduler():
	"""Compatibility entry point retained for older Scheduled Job Type records."""
	return dispatch_reminders()


def _retry_or_fail(doc, error: Exception) -> None:
	attempt = int(doc.attempt_count or 0) + 1
	doc.attempt_count = attempt
	doc.last_error = str(error)[:500]

	if attempt >= MAX_DELIVERY_ATTEMPTS:
		doc.status = "Failed"
	else:
		delay = RETRY_DELAYS_MINUTES[min(attempt - 1, len(RETRY_DELAYS_MINUTES) - 1)]
		doc.status = "Pending"
		doc.remind_at = now_datetime() + timedelta(minutes=delay)

	doc.save(ignore_permissions=True)
	if doc.status == "Pending":
		queue_precise_delivery_after_commit(
			doc.name,
			get_datetime(doc.remind_at),
			doc.recipient or doc.owner,
		)


def _mark_missed_or_advance(reminder_name: str, reason: str) -> dict:
	doc = frappe.get_doc("Reminder Master", reminder_name, for_update=True)
	if doc.status not in {"Pending", "Processing"}:
		return {"status": doc.status, "skipped": True}

	doc.last_error = reason[:500]
	if _should_repeat(doc):
		doc.remind_at = _next_occurrence(doc.remind_at, doc.reminder_interval)
		doc.status = "Pending"
	else:
		doc.status = "Missed"

	doc.save(ignore_permissions=True)
	if doc.status == "Pending":
		queue_precise_delivery_after_commit(
			doc.name,
			get_datetime(doc.remind_at),
			doc.recipient or doc.owner,
		)
	return {"status": doc.status, "missed": True, "reason": reason}


def _should_repeat(doc) -> bool:
	if doc.reminder_type not in RECURRING_REMINDER_TYPES:
		return False

	if doc.reminder_type == "Until Completion":
		if not doc.reminder_for or not frappe.db.exists("Action", doc.reminder_for):
			return False
		return frappe.db.get_value("Action", doc.reminder_for, "status") != "Completed"

	return True


def _next_occurrence(previous, interval) -> object:
	seconds = interval_seconds(interval)
	if seconds <= 0:
		raise NotificationDeliveryError("Recurring reminder has no valid interval")

	next_at = get_datetime(previous) + timedelta(seconds=seconds)
	now = now_datetime()
	while next_at <= now:
		next_at += timedelta(seconds=seconds)
	return next_at


def _load_data(value: str | None) -> dict:
	if not value:
		return {}
	try:
		data = json.loads(value)
	except (TypeError, json.JSONDecodeError):
		return {}
	return data if isinstance(data, dict) else {}


def _affected_rows() -> int:
	return int(getattr(getattr(frappe.db, "_cursor", None), "rowcount", 0) or 0)
