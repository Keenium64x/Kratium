import frappe
from frappe.tests import IntegrationTestCase

from kratium.api import register_device


class TestDeviceRegistration(IntegrationTestCase):
	def tearDown(self):
		frappe.db.delete("FCM Device", {"token": ["like", "codex-browser-token-%"]})
		super().tearDown()

	def test_new_browser_token_is_registered_immediately(self):
		token = "codex-browser-token-new"

		result = register_device(token, "webapp")

		self.assertTrue(result["registered"])
		self.assertTrue(result["created"])
		self.assertTrue(frappe.db.exists("FCM Device", {"token": token}))

	def test_refreshed_browser_token_is_enabled(self):
		token = "codex-browser-token-fresh"

		result = register_device(token, "webapp", refreshed=True)
		device = frappe.get_doc("FCM Device", result["device"])

		self.assertEqual(device.user, "Administrator")
		self.assertEqual(device.device_type, "webapp")
		self.assertEqual(device.enabled, 1)
