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


def send_push(token, title, body, data=None):
    init_firebase()

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        token=token,
    )

    return messaging.send(message)
