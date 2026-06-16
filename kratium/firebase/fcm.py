import firebase_admin
from firebase_admin import credentials, messaging
import frappe


def init_firebase():
    if not firebase_admin._apps:
        path = frappe.conf.get("kratium_firebase_service_account_path")
        if not path:
            frappe.throw("Firebase service account path not configured")

        cred = credentials.Certificate(path)
        firebase_admin.initialize_app(cred)


