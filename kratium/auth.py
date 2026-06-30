import frappe
import jwt
import hashlib
from datetime import datetime, timedelta
from frappe.core.doctype.user.user import User

JWT_ALGO = "HS256"
JWT_EXP_DAYS = 3

def get_jwt_secret():
    secret = frappe.conf.get("jwt_secret")
    if not secret:
        frappe.throw("jwt_secret is not configured")
    return secret

def confirm_credentials(email, password):
    if not email or not password:
        frappe.throw("Email and password are required")

    user = User.find_by_credentials(email, password)
    if not user or not user.is_authenticated:
        frappe.throw("Invalid credentials")
    if user.name != "Administrator" and not user.enabled:
        frappe.throw("User disabled or missing")

    return user

@frappe.whitelist(allow_guest=True)
def login(email, password):
    # 1. Authenticate user
    user = confirm_credentials(email, password)


    # 2. Generate JWT
    payload = {
        "sub": user.name,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=JWT_EXP_DAYS),
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGO)

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # 3. Store / update token
    existing = frappe.db.get_value(
        "Mobile Auth Token", {"user": user.name}, "name"
    )

    if existing:
        # UPDATE existing doc
        doc = frappe.get_doc("Mobile Auth Token", existing)
        doc.token_hash = token_hash
        doc.issued_at = frappe.utils.now()
        doc.expires_at = datetime.utcnow() + timedelta(days=JWT_EXP_DAYS)
        doc.save(ignore_permissions=True)
    else:
        # INSERT new doc
        doc = frappe.get_doc({
            "doctype": "Mobile Auth Token",
            "user": user.name,
            "token_hash": token_hash,
            "issued_at": frappe.utils.now(),
            "expires_at": datetime.utcnow() + timedelta(days=JWT_EXP_DAYS)
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
    existing = doc.name

    return {
        "token": token,
        "user": user.name,
        "exist": existing
    }
