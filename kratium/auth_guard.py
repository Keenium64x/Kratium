import frappe
import jwt
import hashlib
from functools import wraps

JWT_SECRET = frappe.conf.get("jwt_secret")
JWT_ALGO = "HS256"
JWT_HEADER = "X-Mobile-Token"


def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):

        # --- DESK SESSION (read-only) ---
        if frappe.session.user and frappe.session.user != "Guest":
            frappe.local.jwt_user = frappe.session.user
            frappe.local.jwt_auth = "session"
            return fn(*args, **kwargs)

        # --- MOBILE JWT ---
        token = frappe.get_request_header(JWT_HEADER)
        if not token:
            frappe.throw("Unauthorized", frappe.PermissionError)

        try:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGO],
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            frappe.throw("Token expired", frappe.PermissionError)
        except jwt.DecodeError:
            frappe.throw("Invalid token", frappe.PermissionError)

        user = payload["sub"]

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        row = frappe.db.get_value(
            "Mobile Auth Token",
            {
                "user": user,
                "token_hash": token_hash,
            },
            ["name", "expires_at"],
            as_dict=True,
        )

        if not row:
            frappe.throw("Token revoked", frappe.PermissionError)

        if row.expires_at and row.expires_at <= frappe.utils.now_datetime():
            frappe.throw("Token expired", frappe.PermissionError)

        # 🔐 SET ONLY LOCAL CONTEXT
        frappe.local.jwt_user = user
        frappe.local.jwt_auth = "mobile"

        return fn(*args, **kwargs)

    return wrapper
