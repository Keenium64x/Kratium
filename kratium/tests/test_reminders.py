from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from kratium.reminders import interval_seconds, schedule_reminder
from kratium.tasks.reminders import deliver_reminder, dispatch_reminders


class TestReminderScheduling(IntegrationTestCase):
	def tearDown(self):
		frappe.db.delete("Reminder Master", {"name1": ["like", "Codex test%"]})
		super().tearDown()

	def test_interval_parser_supports_human_friendly_values(self):
		self.assertEqual(interval_seconds("1d 2h 30m"), 95400)
		self.assertEqual(interval_seconds("45 seconds"), 45)
		self.assertEqual(interval_seconds(timedelta(minutes=5)), 300)

	def test_schedule_reminder_persists_future_work(self):
		run_at = now_datetime() + timedelta(days=1)
		name = schedule_reminder(
			"Administrator",
			"Codex test tomorrow",
			"A reminder that survives worker restarts",
			run_at,
			data={"importance": "high"},
			route="/kratium/home",
		)

		doc = frappe.get_doc("Reminder Master", name)
		self.assertEqual(doc.status, "Pending")
		self.assertEqual(doc.recipient, "Administrator")
		self.assertEqual(doc.name1, "Codex test tomorrow")
		self.assertEqual(doc.route, "/kratium/home")
		self.assertEqual(doc.remind_at, run_at)
		self.assertIn('"importance":"high"', doc.data_json)

	@patch("kratium.tasks.reminders.send_notification")
	def test_once_reminder_is_fired_only_after_successful_delivery(self, send):
		send.return_value = {
			"devices": 1,
			"success": 1,
			"failure": 0,
			"disabled_tokens": 0,
			"errors": [],
		}
		name = schedule_reminder(
			"Administrator",
			"Codex test once",
			"One delivery",
			now_datetime() - timedelta(minutes=1),
		)
		frappe.db.set_value("Reminder Master", name, "status", "Processing")

		result = deliver_reminder(name, claimed=True)
		doc = frappe.get_doc("Reminder Master", name)

		self.assertEqual(result["status"], "Fired")
		self.assertEqual(doc.status, "Fired")
		self.assertIsNotNone(doc.fired_at)
		self.assertIn('"success": 1', doc.delivery_result)
		send.assert_called_once()

	@patch("kratium.tasks.reminders.send_notification")
	def test_follow_up_schedules_its_next_notification(self, send):
		send.return_value = {
			"devices": 1,
			"success": 1,
			"failure": 0,
			"disabled_tokens": 0,
			"errors": [],
		}
		name = schedule_reminder(
			"Administrator",
			"Codex test follow up",
			"Keep reminding until cancelled",
			now_datetime() - timedelta(minutes=2),
			reminder_type="Follow Up",
			repeat_every="5m",
		)
		frappe.db.set_value("Reminder Master", name, "status", "Processing")

		deliver_reminder(name, claimed=True)
		doc = frappe.get_doc("Reminder Master", name)

		self.assertEqual(doc.status, "Pending")
		self.assertGreater(doc.remind_at, now_datetime())

	@patch("kratium.tasks.reminders.send_notification")
	def test_delivery_failure_is_retried_without_marking_fired(self, send):
		send.side_effect = RuntimeError("temporary Firebase problem")
		name = schedule_reminder(
			"Administrator",
			"Codex test retry",
			"Retry safely",
			now_datetime() - timedelta(minutes=1),
		)
		frappe.db.set_value("Reminder Master", name, "status", "Processing")

		deliver_reminder(name, claimed=True)
		doc = frappe.get_doc("Reminder Master", name)

		self.assertEqual(doc.status, "Pending")
		self.assertEqual(doc.attempt_count, 1)
		self.assertIn("temporary Firebase problem", doc.last_error)
		self.assertGreater(doc.remind_at, now_datetime())

	@patch("kratium.tasks.reminders.ensure_precision_scheduler")
	@patch("kratium.tasks.reminders.schedule_precise_delivery")
	def test_dispatcher_requeues_slightly_late_reminder(self, schedule, ensure):
		name = schedule_reminder(
			"Administrator",
			"Codex test dispatcher",
			"Recover without duplicate delivery",
			now_datetime() - timedelta(seconds=5),
		)

		result = dispatch_reminders()
		doc = frappe.get_doc("Reminder Master", name)

		self.assertGreaterEqual(result["requeued"], 1)
		self.assertEqual(doc.status, "Pending")
		ensure.assert_called_once()
		self.assertTrue(
			any(call.args[0] == name for call in schedule.call_args_list)
		)

	@patch("kratium.tasks.reminders.ensure_precision_scheduler")
	@patch("kratium.tasks.reminders.schedule_precise_delivery")
	def test_dispatcher_marks_stale_one_shot_as_missed(self, schedule, ensure):
		name = schedule_reminder(
			"Administrator",
			"Codex test stale",
			"Do not fire a notification burst",
			now_datetime() - timedelta(minutes=2),
		)

		result = dispatch_reminders()
		doc = frappe.get_doc("Reminder Master", name)

		self.assertGreaterEqual(result["missed"], 1)
		self.assertEqual(doc.status, "Missed")
		self.assertIn("late", doc.last_error)
		self.assertFalse(any(call.args[0] == name for call in schedule.call_args_list))
