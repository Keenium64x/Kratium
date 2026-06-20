import firebase_admin
from firebase_admin import credentials
import frappe


def init_firebase():
	if firebase_admin._apps:
		return firebase_admin.get_app()

	path = frappe.conf.get("kratium_firebase_service_account_path")
	if not path:
		frappe.throw("Firebase service account path not configured")

	cred = credentials.Certificate(path)
	return firebase_admin.initialize_app(cred)
