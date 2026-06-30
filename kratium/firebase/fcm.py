import firebase_admin
from firebase_admin import credentials
import frappe


def get_firebase_service_account_path():
	return frappe.conf.get("kratium_firebase_service_account_path")


def firebase_is_configured():
	path = get_firebase_service_account_path()
	return bool(path and frappe.get_site_path(path) if not str(path).startswith("/") else path)


def init_firebase():
	if firebase_admin._apps:
		return firebase_admin.get_app()

	path = get_firebase_service_account_path()
	if not path:
		frappe.throw(
			"Firebase service account path not configured. Set kratium_firebase_service_account_path in site_config.json."
		)

	if not str(path).startswith("/"):
		path = frappe.get_site_path(path)

	cred = credentials.Certificate(path)
	return firebase_admin.initialize_app(cred)
