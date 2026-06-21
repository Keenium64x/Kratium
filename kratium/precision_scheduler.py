from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime

import frappe
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job
from rq.scheduler import RQScheduler

from frappe.utils.background_jobs import (
	RQ_JOB_FAILURE_TTL,
	RQ_RESULTS_TTL,
	create_job_id,
	get_queue,
	get_queue_list,
	get_redis_conn,
)
from frappe.utils import get_bench_path


PRECISION_JOB_PREFIX = "kratium-precision-reminder"
PRECISION_STARTING_KEY = "kratium:precision-scheduler:starting"


def schedule_precise_delivery(
	reminder_name: str,
	run_at: datetime,
	recipient: str | None = None,
) -> str:
	"""Put a persistent reminder into RQ's delayed-job registry."""
	cancel_precise_delivery(reminder_name)

	queue = get_queue("default")
	job_id = create_job_id(_job_key(reminder_name))
	method = "kratium.tasks.reminders.deliver_reminder"
	queue_args = {
		"site": frappe.local.site,
		"user": recipient or frappe.session.user,
		"method": method,
		"event": None,
		"job_name": method,
		"is_async": True,
		"kwargs": {
			"reminder_name": reminder_name,
			"claimed": False,
		},
	}

	queue.enqueue_at(
		run_at,
		"frappe.utils.background_jobs.execute_job",
		kwargs=queue_args,
		timeout=120,
		failure_ttl=frappe.conf.get("rq_job_failure_ttl") or RQ_JOB_FAILURE_TTL,
		result_ttl=frappe.conf.get("rq_results_ttl") or RQ_RESULTS_TTL,
		job_id=job_id,
	)
	ensure_precision_scheduler()
	return job_id


def cancel_precise_delivery(reminder_name: str) -> bool:
	try:
		job = Job.fetch(
			create_job_id(_job_key(reminder_name)),
			connection=get_redis_conn(),
		)
	except (NoSuchJobError, InvalidJobOperation):
		return False

	job.delete(remove_from_queue=True)
	return True


def queue_precise_delivery_after_commit(
	reminder_name: str,
	run_at: datetime,
	recipient: str | None = None,
) -> None:
	def schedule():
		try:
			schedule_precise_delivery(reminder_name, run_at, recipient)
		except Exception:
			# Reminder Master remains the source of truth. The minute dispatcher
			# is the durable fallback if Redis scheduling is unavailable.
			frappe.log_error(
				title="Could not register precise reminder job",
				message=frappe.get_traceback(),
			)

	frappe.db.after_commit.add(schedule)


def cancel_precise_delivery_after_commit(reminder_name: str) -> None:
	def cancel():
		try:
			cancel_precise_delivery(reminder_name)
		except Exception:
			frappe.log_error(
				title="Could not cancel precise reminder job",
				message=frappe.get_traceback(),
			)

	frappe.db.after_commit.add(cancel)


def run_precision_scheduler() -> None:
	"""Run RQ's one-second delayed-job scheduler for the default queue."""
	with frappe.init_site():
		connection = get_redis_conn()
		queue_names = get_queue_list(["default"], build_queue_name=True)

	scheduler = RQScheduler(
		queue_names,
		connection=connection,
		interval=1,
	)
	scheduler.acquire_locks()
	if not scheduler.acquired_locks:
		return
	scheduler.work()


def ensure_precision_scheduler(wait_seconds: float = 3) -> bool:
	"""Start the precision scheduler when it is not already running."""
	connection = get_redis_conn()
	queue_name = get_queue_list(["default"], build_queue_name=True)[0]
	lock_key = RQScheduler.get_locking_key(queue_name)
	if connection.exists(lock_key):
		return True

	starting = connection.set(PRECISION_STARTING_KEY, "1", nx=True, ex=10)
	if starting:
		_start_precision_scheduler_process()

	deadline = time.monotonic() + wait_seconds
	while time.monotonic() < deadline:
		if connection.exists(lock_key):
			return True
		time.sleep(0.1)
	return False


def _start_precision_scheduler_process() -> None:
	bench = shutil.which("bench")
	if not bench:
		raise RuntimeError("Could not find the bench executable")

	bench_path = get_bench_path()
	log_path = os.path.join(bench_path, "logs", "precision-scheduler.log")
	os.makedirs(os.path.dirname(log_path), exist_ok=True)
	with open(log_path, "ab", buffering=0) as log:
		subprocess.Popen(
			[bench, "precision-scheduler"],
			cwd=bench_path,
			stdin=subprocess.DEVNULL,
			stdout=log,
			stderr=subprocess.STDOUT,
			start_new_session=True,
			close_fds=True,
		)


def _job_key(reminder_name: str) -> str:
	return f"{PRECISION_JOB_PREFIX}-{reminder_name}"
