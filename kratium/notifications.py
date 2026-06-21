from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import frappe
from firebase_admin import messaging

from kratium.firebase.fcm import init_firebase


MAX_FCM_TOKENS = 500
WEB_DEVICE_TYPES = {"web", "webapp"}
INVALID_TOKEN_CODES = {
	"invalid-argument",
	"messaging/invalid-registration-token",
	"messaging/registration-token-not-registered",
	"not_found",
	"registration-token-not-registered",
	"unregistered",
}


class NotificationDeliveryError(RuntimeError):
	pass


@dataclass(frozen=True)
class Notification:
	user: str
	title: str
	body: str
	data: dict[str, Any] = field(default_factory=dict)
	route: str | None = None
	event_type: str = "notification"
	notification_id: str | None = None

	def fcm_data(self) -> dict[str, str]:
		payload = normalize_data(self.data)
		payload.update(
			{
				"schema_version": "1",
				"event_type": self.event_type,
				"title": clean_title(self.title),
				"body": clean_body(self.body),
			}
		)

		if self.route:
			payload["route"] = str(self.route)
		if self.notification_id:
			payload["notification_id"] = str(self.notification_id)

		return payload


def clean_title(title: Any) -> str:
	value = str(title or "").strip()
	return value or "Kratium"


def clean_body(body: Any) -> str:
	return str(body or "").strip()


def normalize_data(data: dict[str, Any] | str | None) -> dict[str, str]:
	if not data:
		return {}

	if isinstance(data, str):
		try:
			data = json.loads(data)
		except json.JSONDecodeError as error:
			raise ValueError("Notification data must be valid JSON") from error

	if not isinstance(data, dict):
		raise TypeError("Notification data must be a dictionary")

	payload = {}
	for key, value in data.items():
		if value is None:
			continue
		if isinstance(value, (dict, list, tuple)):
			payload[str(key)] = json.dumps(value, separators=(",", ":"), default=str)
		elif isinstance(value, bool):
			payload[str(key)] = "true" if value else "false"
		else:
			payload[str(key)] = str(value)
	return payload


def build_multicast_message(
	notification: Notification,
	tokens: list[str],
	*,
	web: bool = False,
) -> messaging.MulticastMessage:
	data = notification.fcm_data()
	title = data["title"]
	body = data["body"]

	if web:
		# The existing service worker displays data messages itself. Keeping web
		# data-only prevents Firebase and the service worker showing duplicates.
		return messaging.MulticastMessage(
			tokens=tokens,
			data=data,
			webpush=messaging.WebpushConfig(headers={"Urgency": "high"}),
		)

	return messaging.MulticastMessage(
		tokens=tokens,
		data=data,
		notification=messaging.Notification(title=title, body=body),
		android=messaging.AndroidConfig(
			priority="high",
			notification=messaging.AndroidNotification(
				title=title,
				body=body,
				default_sound=True,
				default_vibrate_timings=True,
				visibility="public",
			),
		),
		apns=messaging.APNSConfig(
			headers={"apns-priority": "10"},
			payload=messaging.APNSPayload(
				aps=messaging.Aps(
					sound="default",
					content_available=True,
					mutable_content=True,
				)
			),
		),
	)


def send_notification(
	notification: Notification,
	*,
	raise_on_total_failure: bool = False,
) -> dict[str, Any]:
	devices = frappe.get_all(
		"FCM Device",
		filters={"user": notification.user, "enabled": 1},
		fields=["name", "token", "device_type"],
		limit=2000,
	)

	if not devices:
		result = {
			"devices": 0,
			"success": 0,
			"failure": 0,
			"disabled_tokens": 0,
			"errors": [],
			"deliveries": [],
		}
		if raise_on_total_failure:
			raise NotificationDeliveryError(f"No enabled devices for {notification.user}")
		return result

	init_firebase()

	result = {
		"devices": len(devices),
		"success": 0,
		"failure": 0,
		"disabled_tokens": 0,
		"errors": [],
		"deliveries": [],
	}

	web_devices = [device for device in devices if device.device_type in WEB_DEVICE_TYPES]
	native_devices = [device for device in devices if device.device_type not in WEB_DEVICE_TYPES]

	for group, is_web in ((web_devices, True), (native_devices, False)):
		for start in range(0, len(group), MAX_FCM_TOKENS):
			batch = group[start : start + MAX_FCM_TOKENS]
			_send_batch(notification, batch, result, web=is_web)

	if result["errors"]:
		frappe.log_error(
			title="Kratium notification delivery failures",
			message=json.dumps(result["errors"], indent=2, default=str),
		)

	if raise_on_total_failure and result["success"] == 0:
		raise NotificationDeliveryError(
			f"Notification delivery failed for all {result['devices']} devices"
		)

	return result


def _send_batch(
	notification: Notification,
	devices: list[Any],
	result: dict[str, Any],
	*,
	web: bool,
) -> None:
	message = build_multicast_message(
		notification,
		[device.token for device in devices],
		web=web,
	)
	response = messaging.send_each_for_multicast(message)

	result["success"] += response.success_count
	result["failure"] += response.failure_count

	for index, send_response in enumerate(response.responses):
		device = devices[index]
		if send_response.success:
			result["deliveries"].append(
				{
					"device": device.name,
					"device_type": device.device_type,
					"success": True,
				}
			)
			continue

		code = _error_code(send_response.exception)
		error_text = str(send_response.exception)
		delivery = {
			"device": device.name,
			"device_type": device.device_type,
			"success": False,
			"code": code,
			"error": error_text,
		}
		result["deliveries"].append(delivery)
		result["errors"].append(delivery)

		if _is_invalid_token(code, error_text):
			frappe.db.set_value("FCM Device", device.name, "enabled", 0, update_modified=False)
			result["disabled_tokens"] += 1


def _error_code(error: Exception | None) -> str:
	if not error:
		return "unknown"
	return str(getattr(error, "code", "") or getattr(error, "status", "") or "unknown").lower()


def _is_invalid_token(code: str, error_text: str = "") -> bool:
	error_text = error_text.lower()
	return (
		code in INVALID_TOKEN_CODES
		or any(value in code for value in INVALID_TOKEN_CODES)
		or "device unregistered" in error_text
		or "registration token is not registered" in error_text
	)


def enqueue_notification(
	user: str,
	title: str,
	body: str,
	data: dict[str, Any] | str | None = None,
	route: str | None = None,
	event_type: str = "notification",
	notification_id: str | None = None,
) -> Any:
	return frappe.enqueue(
		method="kratium.notifications.send_notification_job",
		queue="default",
		timeout=120,
		enqueue_after_commit=True,
		user=user,
		title=title,
		body=body,
		data=data,
		route=route,
		event_type=event_type,
		notification_id=notification_id,
	)


def send_notification_job(
	user: str,
	title: str,
	body: str,
	data: dict[str, Any] | str | None = None,
	route: str | None = None,
	event_type: str = "notification",
	notification_id: str | None = None,
) -> dict[str, Any]:
	return send_notification(
		Notification(
			user=user,
			title=title,
			body=body,
			data=normalize_data(data),
			route=route,
			event_type=event_type,
			notification_id=notification_id,
		)
	)
