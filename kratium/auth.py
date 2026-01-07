import frappe
import jwt
import hashlib
from datetime import datetime, timedelta
import requests

JWT_SECRET = frappe.conf.get("jwt_secret")  # put in site_config.json
JWT_ALGO = "HS256"
JWT_EXP_DAYS = 90

def confirm_credentials(email, password):
    base = frappe.conf.host_name or "kratium.localhost:8003"


    url = f"http://{base}/api/method/login"

    r = requests.post(
        url,
        data={
            "usr": email,
            "pwd": password,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )

    if r.status_code != 200:
        frappe.throw("Invalid credentials")

    return frappe.get_doc("User", email)

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
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

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