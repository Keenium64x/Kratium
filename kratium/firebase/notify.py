from kratium.notifications import Notification, send_notification


def notify_user(user, title, body, data=None):
	"""Compatibility wrapper for older imports."""
	return send_notification(
		Notification(user=user, title=title, body=body, data=data or {})
	)
