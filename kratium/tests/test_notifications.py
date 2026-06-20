from frappe.tests import IntegrationTestCase

from kratium.notifications import Notification, build_multicast_message, normalize_data


class TestNotificationPayload(IntegrationTestCase):
	def test_normalize_data_converts_every_value_to_fcm_strings(self):
		self.assertEqual(
			normalize_data(
				{
					"count": 2,
					"enabled": True,
					"actions": [{"id": "complete"}],
					"ignored": None,
				}
			),
			{
				"count": "2",
				"enabled": "true",
				"actions": '[{"id":"complete"}]',
			},
		)

	def test_native_message_has_visible_and_data_payloads(self):
		message = build_multicast_message(
			Notification(
				user="Administrator",
				title="Follow up",
				body="Call the supplier",
				route="/kratium/home",
				event_type="reminder",
				notification_id="REM-1",
			),
			["native-token"],
		)

		self.assertEqual(message.notification.title, "Follow up")
		self.assertEqual(message.notification.body, "Call the supplier")
		self.assertEqual(message.data["title"], "Follow up")
		self.assertEqual(message.data["body"], "Call the supplier")
		self.assertEqual(message.data["route"], "/kratium/home")
		self.assertEqual(message.data["notification_id"], "REM-1")
		self.assertEqual(message.android.priority, "high")
		self.assertEqual(message.apns.payload.aps.sound, "default")

	def test_web_message_stays_data_only_for_service_worker(self):
		message = build_multicast_message(
			Notification(
				user="Administrator",
				title="Desktop reminder",
				body="Visible description",
			),
			["web-token"],
			web=True,
		)

		self.assertIsNone(message.notification)
		self.assertEqual(message.data["title"], "Desktop reminder")
		self.assertEqual(message.data["body"], "Visible description")
