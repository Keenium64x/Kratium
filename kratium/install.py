import frappe
import secrets
from frappe.installer import update_site_config

def after_install():
    if not frappe.conf.get("jwt_secret"):
        secret = secrets.token_hex(64)  # 128-char hex
        frappe.conf["jwt_secret"] = secret
        frappe.local.conf.jwt_secret = secret
        update_site_config("jwt_secret", secret)
