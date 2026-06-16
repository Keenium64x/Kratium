import frappe
from firebase_admin import messaging
from kratium.firebase.fcm import init_firebase

def notify_user(user, title, body, data=None):
    init_firebase()

    tokens = frappe.get_all(
        "FCM Device",
        filters={"user": user, "enabled": 1},
        pluck="token",
    )

    if not tokens:
        return "No devices"

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        tokens=tokens,
    )

    return messaging.send_each_for_multicast(message)
