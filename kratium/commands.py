import click

from kratium.precision_scheduler import run_precision_scheduler


@click.command("precision-scheduler")
def precision_scheduler():
	"""Run Kratium's second-level delayed reminder scheduler."""
	run_precision_scheduler()


commands = [precision_scheduler]
