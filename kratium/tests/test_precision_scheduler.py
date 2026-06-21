from datetime import timedelta
from unittest.mock import MagicMock, patch

from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from kratium.precision_scheduler import schedule_precise_delivery


class TestPrecisionScheduler(IntegrationTestCase):
	@patch("kratium.precision_scheduler.ensure_precision_scheduler")
	@patch("kratium.precision_scheduler.cancel_precise_delivery")
	@patch("kratium.precision_scheduler.get_queue")
	def test_schedules_frappe_job_at_exact_datetime(self, get_queue, cancel, ensure):
		queue = MagicMock()
		get_queue.return_value = queue
		run_at = now_datetime() + timedelta(seconds=10)

		job_id = schedule_precise_delivery(
			"REM-TEST-1",
			run_at,
			"Administrator",
		)

		cancel.assert_called_once_with("REM-TEST-1")
		ensure.assert_called_once()
		queue.enqueue_at.assert_called_once()
		args, kwargs = queue.enqueue_at.call_args
		self.assertEqual(args[0], run_at)
		self.assertEqual(args[1], "frappe.utils.background_jobs.execute_job")
		self.assertEqual(
			kwargs["kwargs"]["kwargs"],
			{"reminder_name": "REM-TEST-1", "claimed": False},
		)
		self.assertIn("REM-TEST-1", job_id)
